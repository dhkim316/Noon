import json
import os
import shutil
import socket
import threading
import time

from monitor import BAUDRATE as PRINTER_BAUDRATE
from monitor import PORT as PRINTER_PORT
from monitor import SerialReceiver
from monitor import wait_for_status_sequence


HOST = "0.0.0.0"
PORT = 5000
SERVER_ID = "MINIPC-001"
MAX_CLIENTS = 3
# KIOSK_HOST = "127.0.0.1"
KIOSK_HOST = "192.168.0.3"
KIOSK_PORT = 8001
KIOSK_RECONNECT_DELAY_S = 2.0
PRINT_IMAGE_SOURCE = r"C:\hnb\image\111.png"
PRINT_IMAGE_TARGET_DIR = r"C:\PartnerDRV\Temp"
PRINT_IMAGE_TARGET = os.path.join(PRINT_IMAGE_TARGET_DIR, os.path.basename(PRINT_IMAGE_SOURCE))
PRINTER_STATUS_SEQUENCE = ["Printing", "Finish"]
PRINTER_STATUS_TIMEOUT_S = 120
PRINTER_KEEPALIVE_INTERVAL_S = 1.0
NODE_RECONNECT_WAIT_S = 15
SELF_CHECK_SENSOR_TIMEOUT_S = 10
SELF_CHECK_PRINTER_TIMEOUT_S = 3.0
CHUTE_AUTO_CLOSE_DELAY_S = 30.0
EMERGENCY_STOP_BUSY_WINDOW_S = 60.0
DEFAULT_FILL_MS = {
    "f1": {"f1": 1000},
    "f2": {"f2": 500, "f1": 1000},
    "f3": {"f3": 500, "f1": 1000},
    "f4": {"f4": 500, "f1": 1000},
}


class ClientRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._clients = {}

    def set(self, node_id, conn, addr):
        with self._lock:
            old = self._clients.get(node_id)
            self._clients[node_id] = {"conn": conn, "addr": addr}
        return old

    def remove_by_conn(self, conn):
        with self._lock:
            for node_id, info in list(self._clients.items()):
                if info["conn"] is conn:
                    del self._clients[node_id]
                    return node_id
        return None

    def get(self, node_id):
        with self._lock:
            return self._clients.get(node_id)

    def count(self):
        with self._lock:
            return len(self._clients)

    def list(self):
        with self._lock:
            return {node_id: info["addr"] for node_id, info in self._clients.items()}


REGISTRY = ClientRegistry()


class ResponseTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._seq = 0
        self._events = []

    def push(self, node_id, msg):
        with self._cond:
            self._seq += 1
            self._events.append((self._seq, node_id, msg))
            self._cond.notify_all()

    def snapshot(self):
        with self._lock:
            return self._seq

    def wait_for(self, after_seq, node_id, op, timeout_s):
        with self._cond:
            end_time = time.time() + timeout_s
            while True:
                for seq, event_node, msg in self._events:
                    if seq <= after_seq:
                        continue
                    if event_node != node_id:
                        continue
                    if msg.get("t") != "resp":
                        continue
                    if msg.get("op") != op:
                        continue
                    return msg

                remaining = end_time - time.time()
                if remaining <= 0:
                    raise TimeoutError("timeout waiting for {} {}".format(node_id, op))
                self._cond.wait(remaining)


RESPONSES = ResponseTracker()
NODE_C1_FIRST_PICK_LOCK = threading.Lock()
NODE_C1_FIRST_PICK_SENT = False


def canonical_node_id(node_id):
    value = str(node_id or "").strip().upper()
    aliases = {
        "NODE_A": "NODE_A",
        "NODE-A": "NODE_A",
        "NODE_C": "NODE_C",
        "NODE-C": "NODE_C",
        "NODE_C1": "NODE_C1",
        "NODE-C1": "NODE_C1",
    }
    return aliases.get(value, value)


def make_msg(msg_type, op, data, dst, src=SERVER_ID):
    return {"t": msg_type, "from": src, "to": dst, "op": op, "d": data}


def now_ms():
    return int(time.time() * 1000)


def to_wire(msg):
    return (json.dumps(msg) + "\n").encode("utf-8")


def send_msg(conn, msg):
    conn.sendall(to_wire(msg))
    print("TX:", msg)


def recv_loop(conn, addr):
    buf = b""
    registered = None

    try:
        while True:
            chunk = conn.recv(2048)
            if not chunk:
                break
            buf += chunk
            while True:
                idx = buf.find(b"\n")
                if idx < 0:
                    break
                line = buf[:idx].strip()
                buf = buf[idx + 1 :]
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception as exc:
                    print("bad json from {}:{} -> {}".format(addr[0], addr[1], exc))
                    continue

                src = canonical_node_id(msg.get("from"))
                if msg.get("op") == "hello" and src in ("NODE_A", "NODE_C", "NODE_C1"):
                    old = REGISTRY.set(src, conn, addr)
                    registered = src
                    should_send_first_pick = False
                    if old and old["conn"] is not conn:
                        print("replacing existing connection for {}".format(src))
                        try:
                            old["conn"].close()
                        except Exception:
                            pass
                    print("registered {} from {}:{}".format(src, addr[0], addr[1]))
                    if src == "NODE_C1":
                        global NODE_C1_FIRST_PICK_SENT
                        with NODE_C1_FIRST_PICK_LOCK:
                            if not NODE_C1_FIRST_PICK_SENT:
                                NODE_C1_FIRST_PICK_SENT = True
                                should_send_first_pick = True
                    if should_send_first_pick:
                        try:
                            send_to("NODE_C1", "bottle.pick")
                            print("NODE_C1 first connect -> bottle.pick sent")
                        except Exception as exc:
                            with NODE_C1_FIRST_PICK_LOCK:
                                NODE_C1_FIRST_PICK_SENT = False
                            print("NODE_C1 first connect bottle.pick error:", exc)

                tag = registered or src or "{}:{}".format(addr[0], addr[1])
                print("RX[{}]: {}".format(tag, msg))
                if src in ("NODE_A", "NODE_C", "NODE_C1"):
                    RESPONSES.push(src, msg)
    except OSError as exc:
        print("recv error from {}:{} -> {}".format(addr[0], addr[1], exc))
    finally:
        node_id = REGISTRY.remove_by_conn(conn)
        if node_id:
            print("{} disconnected".format(node_id))
        else:
            print("client disconnected from {}:{}".format(addr[0], addr[1]))
        try:
            conn.close()
        except Exception:
            pass


def accept_loop(server):
    while True:
        conn, addr = server.accept()
        print("client connected from {}:{}".format(addr[0], addr[1]))
        thread = threading.Thread(target=recv_loop, args=(conn, addr), daemon=True)
        thread.start()


def send_to(node_id, op, data=None):
    node_id = canonical_node_id(node_id)
    info = REGISTRY.get(node_id)
    if not info:
        raise RuntimeError("{} not connected".format(node_id))
    send_msg(info["conn"], make_msg("req", op, data or {}, dst=node_id))


def send_and_wait(node_id, op, data=None, timeout_s=180):
    after_seq = RESPONSES.snapshot()
    send_to(node_id, op, data=data)
    resp = RESPONSES.wait_for(after_seq, node_id, op, timeout_s)
    payload = resp.get("d")
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError("{} {} failed: {}".format(node_id, op, payload.get("msg", "unknown")))
    return resp


def send_and_wait_raw(node_id, op, data=None, timeout_s=180):
    after_seq = RESPONSES.snapshot()
    send_to(node_id, op, data=data)
    return RESPONSES.wait_for(after_seq, node_id, op, timeout_s)


def ensure_node_a_drop_one(timeout_s=180):
    resp = send_and_wait_raw("NODE_A", "bottle.drop_one", timeout_s=timeout_s)
    payload = resp.get("d")
    if not (isinstance(payload, dict) and payload.get("ok") is False):
        return resp

    print("NODE_A bottle.drop_one returned ok:false -> retry after bottle.on_the_conveyor")
    send_and_wait("NODE_A", "bottle.on_the_conveyor", timeout_s=timeout_s)

    retry_resp = send_and_wait_raw("NODE_A", "bottle.drop_one", timeout_s=timeout_s)
    retry_payload = retry_resp.get("d")
    if isinstance(retry_payload, dict) and retry_payload.get("ok") is False:
        raise RuntimeError(
            "NODE_A bottle.drop_one failed after retry: {}".format(
                retry_payload.get("msg", "ok false")
            )
        )
    return retry_resp


def sensor_payload_to_map(payload):
    if isinstance(payload, list):
        result = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if name is not None:
                result[str(name)] = value
        return result
    if isinstance(payload, dict):
        return payload
    return {}


def wait_sensor_value(node_id, sensor_name, expected, timeout_s=30, poll_s=0.5):
    end_time = time.time() + timeout_s
    while time.time() < end_time:
        resp = send_and_wait(node_id, "sensor.state", timeout_s=30)
        sensor_map = sensor_payload_to_map(resp.get("d"))
        value = sensor_map.get(sensor_name)
        print("sensor check {} {}={}".format(node_id, sensor_name, value))
        if value == expected:
            return resp
        time.sleep(poll_s)
    raise TimeoutError("timeout waiting for {} {}={}".format(node_id, sensor_name, expected))


def wait_node_connected(node_id, timeout_s=NODE_RECONNECT_WAIT_S, poll_s=0.2):
    node_id = canonical_node_id(node_id)
    end_time = time.time() + timeout_s
    while time.time() < end_time:
        if REGISTRY.get(node_id):
            return True
        time.sleep(poll_s)
    raise TimeoutError("timeout waiting for {} reconnect".format(node_id))


def copy_print_image():
    if not os.path.isfile(PRINT_IMAGE_SOURCE):
        raise FileNotFoundError("print image not found: {}".format(PRINT_IMAGE_SOURCE))

    os.makedirs(PRINT_IMAGE_TARGET_DIR, exist_ok=True)
    shutil.copyfile(PRINT_IMAGE_SOURCE, PRINT_IMAGE_TARGET)
    print("print image copied: {} -> {}".format(PRINT_IMAGE_SOURCE, PRINT_IMAGE_TARGET))


def wait_printer_finish():
    print("waiting printer status:", " -> ".join(PRINTER_STATUS_SEQUENCE))
    last_ping_at = [0.0]

    def keepalive():
        now = time.time()
        if now - last_ping_at[0] < PRINTER_KEEPALIVE_INTERVAL_S:
            return
        last_ping_at[0] = now
        for node_id in ("NODE_A", "NODE_C", "NODE_C1"):
            info = REGISTRY.get(node_id)
            if not info:
                continue
            try:
                send_msg(info["conn"], make_msg("ping", "ping", {}, dst=node_id))
            except Exception as exc:
                print("printer wait ping error {}: {}".format(node_id, exc))

    events = wait_for_status_sequence(
        PRINTER_STATUS_SEQUENCE,
        timeout_s=PRINTER_STATUS_TIMEOUT_S,
        tick_s=0.2,
        on_tick=keepalive,
    )
    for evt in events:
        print("printer status {} {}".format(evt.get("device"), evt.get("status")))
    return events


def make_fill_payload(flavor):
    if flavor not in DEFAULT_FILL_MS:
        raise ValueError("invalid flavor")
    return {"fill_ms": dict(DEFAULT_FILL_MS[flavor])}


def read_printer_status(timeout_s=SELF_CHECK_PRINTER_TIMEOUT_S):
    event = {}
    ready = threading.Event()
    rx = None

    def on_event(evt):
        if ready.is_set():
            return
        event["value"] = evt
        ready.set()

    try:
        rx = SerialReceiver(
            port=PRINTER_PORT,
            baudrate=PRINTER_BAUDRATE,
            on_event=on_event,
        )
        rx.start()
        if not ready.wait(timeout_s):
            raise TimeoutError("timeout waiting for printer status")
        return event["value"]
    finally:
        if rx:
            rx.stop()
            rx.join(timeout=1)


def build_self_check_data():
    items = []

    for node_id in ("NODE_A", "NODE_C", "NODE_C1"):
        try:
            resp = send_and_wait(node_id, "sensor.state", timeout_s=SELF_CHECK_SENSOR_TIMEOUT_S)
            items.append(
                {
                    "name": "{}.sensors".format(node_id),
                    "status": "PASS",
                    "detail": sensor_payload_to_map(resp.get("d")),
                }
            )
        except Exception as exc:
            items.append(
                {
                    "name": "{}.sensors".format(node_id),
                    "status": "FAIL",
                    "code": "NODE_SENSOR_ERROR",
                    "detail": str(exc),
                }
            )

    try:
        printer = read_printer_status()
        items.append(
            {
                "name": "printer",
                "status": "PASS",
                "detail": {
                    "device": printer.get("device"),
                    "status": printer.get("status"),
                    "raw": printer.get("raw"),
                },
            }
        )
    except Exception as exc:
        items.append(
            {
                "name": "printer",
                "status": "FAIL",
                "code": "PRINTER_STATUS_ERROR",
                "detail": str(exc),
            }
        )

    overall = "PASS" if all(item.get("status") == "PASS" for item in items) else "FAIL"
    return {"overall": overall, "items": items}


def run_make_cycle(flavor, side, hooks=None):
    hooks = hooks or {}
    if flavor not in ("f1", "f2", "f3", "f4"):
        raise ValueError("invalid flavor")
    if side not in ("left", "right"):
        raise ValueError("invalid side")

    print("make cycle start:", flavor, side)
    on_start = hooks.get("on_start")
    if on_start:
        on_start(flavor, side)
    ensure_node_a_drop_one()
    send_and_wait("NODE_C1", "bottle.go_printer")
    on_printer_arrived = hooks.get("on_printer_arrived")
    if on_printer_arrived:
        on_printer_arrived(flavor, side)
    copy_print_image()
    wait_printer_finish()
    wait_node_connected("NODE_C1")
    send_and_wait("NODE_C1", "bottle.pick")
    wait_node_connected("NODE_C")
    send_and_wait("NODE_C", "bottle.fill.{}.{}".format(flavor, side), data=make_fill_payload(flavor))

    if side == "left":
        send_and_wait("NODE_C1", "door.open_left")
        wait_sensor_value("NODE_C", "S9_left_bottle", 0)
        time.sleep(5)
        send_and_wait("NODE_C1", "door.close_left")
    else:
        send_and_wait("NODE_C1", "door.open_right")
        wait_sensor_value("NODE_C", "S10_right_bottle", 0)
        time.sleep(5)
        send_and_wait("NODE_C1", "door.close_right")

    on_done = hooks.get("on_done")
    if on_done:
        on_done(flavor, side)
    print("make cycle done:", flavor, side)


class KioskBridge:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.sock_file = None
        self.send_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.chute_timer_lock = threading.Lock()
        self.chute_close_timers = {"L": None, "R": None}
        self.running = True
        self.job_busy = False
        self.current_job_id = None
        self.last_emergency_stop_at = 0.0
        self.evt_seq = 0

    def start(self):
        thread = threading.Thread(target=self.connect_loop, daemon=True)
        thread.start()

    def next_evt_id(self):
        with self.state_lock:
            self.evt_seq += 1
            return "e-{}".format(self.evt_seq)

    def make_base(self, msg_type, msg_id, cmd, data):
        return {
            "v": 1,
            "type": msg_type,
            "id": str(msg_id),
            "ts": now_ms(),
            "from": SERVER_ID,
            "cmd": cmd,
            "data": data,
        }

    def send(self, msg):
        payload = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        with self.send_lock:
            if not self.sock:
                raise RuntimeError("kiosk not connected")
            self.sock.sendall(payload)
        print("KIOSK TX:", msg)

    def send_resp(self, req, code, detail="0", data=None):
        msg = self.make_base("resp", req.get("id", ""), req.get("cmd", ""), data or {})
        msg["result"] = {"code": code, "detail": str(detail)}
        self.send(msg)

    def send_evt(self, cmd, data):
        self.send(self.make_base("evt", self.next_evt_id(), cmd, data))

    def send_evt_safe(self, cmd, data):
        try:
            self.send_evt(cmd, data)
        except Exception as exc:
            print("kiosk evt send error {}: {}".format(cmd, exc))

    def connect_loop(self):
        while self.running:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                print("kiosk connect target {}:{}".format(self.host, self.port))
                sock.connect((self.host, self.port))
                sock.settimeout(None)
                with self.send_lock:
                    self.sock = sock
                self.sock_file = sock.makefile("r", encoding="utf-8", newline="\n")
                print("kiosk connected {}:{}".format(self.host, self.port))
                self.recv_loop()
            except OSError as exc:
                print("kiosk connect error:", exc)
                time.sleep(KIOSK_RECONNECT_DELAY_S)
            finally:
                try:
                    if self.sock_file:
                        self.sock_file.close()
                except OSError:
                    pass
                self.sock_file = None
                with self.send_lock:
                    old = self.sock
                    self.sock = None
                try:
                    if old:
                        old.close()
                except OSError:
                    pass

    def recv_loop(self):
        while self.running and self.sock_file:
            line = self.sock_file.readline()
            if not line:
                print("kiosk disconnected")
                return
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError as exc:
                print("kiosk bad json:", exc, line)
                continue
            print("KIOSK RX:", msg)
            self.handle_msg(msg)

    def handle_msg(self, msg):
        if msg.get("type") != "req":
            return
        cmd = msg.get("cmd")
        if cmd == "bottle.start":
            self.handle_bottle_start(msg)
            return
        if cmd == "sys.emergency_stop":
            self.handle_emergency_stop(msg)
            return
        if cmd == "sys.self_check":
            self.handle_self_check(msg)
            return
        if cmd == "chute.open":
            self.handle_chute_open(msg)
            return
        if cmd == "chute.close":
            self.handle_chute_close(msg)
            return
        self.send_resp(msg, "NOT_SUPPORTED", "unsupported command", {})

    def handle_bottle_start(self, req):
        data = req.get("data") or {}
        job_id = str(data.get("job_id") or "")
        flavor = str(data.get("flavor") or "f1").lower()
        side_raw = str(data.get("side") or "").upper()
        side = {"L": "left", "R": "right"}.get(side_raw)

        if not job_id:
            self.send_resp(req, "INVALID_PARAM", "missing job_id", {"accepted": False})
            return
        if flavor not in ("f1", "f2", "f3", "f4"):
            self.send_resp(req, "INVALID_PARAM", "invalid flavor", {"job_id": job_id, "accepted": False})
            return
        if side is None:
            self.send_resp(req, "INVALID_PARAM", "invalid side", {"job_id": job_id, "accepted": False})
            return

        missing = [node_id for node_id in ("NODE_A", "NODE_C", "NODE_C1") if not REGISTRY.get(node_id)]
        if missing:
            self.send_resp(
                req,
                "INVALID_STATE",
                "missing nodes: {}".format(",".join(missing)),
                {"job_id": job_id, "accepted": False},
            )
            return

        with self.state_lock:
            if self.job_busy:
                self.send_resp(req, "BUSY", "job in progress", {"job_id": job_id, "accepted": False})
                return
            self.job_busy = True
            self.current_job_id = job_id

        self.send_resp(req, "OK", "0", {"job_id": job_id, "accepted": True})
        thread = threading.Thread(target=self.run_bottle_start_job, args=(job_id, flavor, side, side_raw), daemon=True)
        thread.start()

    def run_bottle_start_job(self, job_id, flavor, side, side_raw):
        try:
            run_make_cycle(
                flavor,
                side,
                hooks={
                    "on_start": lambda _flavor, _side: self.on_job_start(job_id, side_raw),
                    "on_printer_arrived": lambda _flavor, _side: self.on_job_printer_arrived(job_id),
                    "on_done": lambda _flavor, _side: self.on_job_done(job_id, side_raw),
                },
            )
        except Exception as exc:
            self.send_evt_safe(
                "bottle.state",
                {
                    "job_id": job_id,
                    "state": "ERROR",
                    "message": str(exc),
                    "error": {"code": "INTERNAL_ERROR", "detail": str(exc)},
                },
            )
        finally:
            with self.state_lock:
                self.job_busy = False
                self.current_job_id = None

    def on_job_start(self, job_id, side):
        self.send_evt_safe("bottle.state", {"job_id": job_id, "state": "CREATING"})
        self.send_evt_safe("bottle.stage", {"job_id": job_id, "stage": "START", "side": side})

    def on_job_printer_arrived(self, job_id):
        self.send_evt_safe("bottle.printer_arrived", {"job_id": job_id, "arrived": True})
        self.send_evt_safe("bottle.stage", {"job_id": job_id, "stage": "PRINTER_ARRIVED"})

    def on_job_done(self, job_id, side):
        self.send_evt_safe("bottle.stage", {"job_id": job_id, "stage": "CHUTE_ARRIVED", "side": side})
        self.send_evt_safe("bottle.state", {"job_id": job_id, "state": "DONE"})

    def cancel_chute_auto_close(self, side_raw):
        with self.chute_timer_lock:
            timer = self.chute_close_timers.get(side_raw)
            self.chute_close_timers[side_raw] = None
        if timer:
            timer.cancel()

    def schedule_chute_auto_close(self, side_raw):
        self.cancel_chute_auto_close(side_raw)

        timer = None

        def auto_close():
            self.run_chute_auto_close(side_raw, timer)

        timer = threading.Timer(CHUTE_AUTO_CLOSE_DELAY_S, auto_close)
        timer.daemon = True

        with self.chute_timer_lock:
            self.chute_close_timers[side_raw] = timer

        timer.start()

    def run_chute_auto_close(self, side_raw, timer):
        with self.chute_timer_lock:
            current = self.chute_close_timers.get(side_raw)
            if current is not timer:
                return
            self.chute_close_timers[side_raw] = None

        op = "door.close_left" if side_raw == "L" else "door.close_right"

        try:
            send_and_wait("NODE_C1", op)
            print("auto chute close done:", side_raw)
        except Exception as exc:
            print("auto chute close error {}: {}".format(side_raw, exc))

    def handle_emergency_stop(self, req):
        data = req.get("data") or {}
        job_id = str(data.get("job_id") or "")
        now = time.monotonic()
        busy_data = None

        with self.state_lock:
            elapsed = now - self.last_emergency_stop_at
            if elapsed < EMERGENCY_STOP_BUSY_WINDOW_S:
                remaining = EMERGENCY_STOP_BUSY_WINDOW_S - elapsed
                retry_after_s = max(1, int(remaining + 0.999))
                busy_data = {"stopped": False, "retry_after_s": retry_after_s}
            else:
                self.last_emergency_stop_at = now
                if not job_id:
                    job_id = str(self.current_job_id or "")

        if busy_data is not None:
            self.send_resp(req, "BUSY", "emergency stop cooldown", busy_data)
            return

        resp_data = {"stopped": True}
        if job_id:
            resp_data["job_id"] = job_id

        self.send_resp(req, "OK", "0", resp_data)

        thread = threading.Thread(target=self.run_emergency_stop, daemon=True)
        thread.start()

    def run_emergency_stop(self):
        for node_id in ("NODE_A", "NODE_C", "NODE_C1"):
            try:
                send_to(node_id, "reboot")
            except Exception as exc:
                print("emergency stop reboot dispatch error {}: {}".format(node_id, exc))

    def handle_self_check(self, req):
        try:
            self.send_resp(req, "OK", "0", build_self_check_data())
        except Exception as exc:
            self.send_resp(
                req,
                "INTERNAL_ERROR",
                str(exc),
                {
                    "overall": "FAIL",
                    "items": [
                        {
                            "name": "self_check",
                            "status": "FAIL",
                            "code": "INTERNAL_ERROR",
                            "detail": str(exc),
                        }
                    ],
                },
            )

    def handle_chute_open(self, req):
        data = req.get("data") or {}
        side_raw = str(data.get("side") or "").upper()
        side = {"L": "left", "R": "right"}.get(side_raw)
        if side is None:
            self.send_resp(req, "INVALID_PARAM", "invalid side", {})
            return

        op = "door.open_left" if side == "left" else "door.open_right"

        try:
            send_and_wait("NODE_C1", op)
            self.schedule_chute_auto_close(side_raw)
            self.send_resp(req, "OK", "0", {"side": side_raw, "opened": True})
        except Exception as exc:
            self.send_resp(req, "INTERNAL_ERROR", str(exc), {"side": side_raw, "opened": False})

    def handle_chute_close(self, req):
        data = req.get("data") or {}
        side_raw = str(data.get("side") or "").upper()
        side = {"L": "left", "R": "right"}.get(side_raw)
        if side is None:
            self.send_resp(req, "INVALID_PARAM", "invalid side", {})
            return

        op = "door.close_left" if side == "left" else "door.close_right"

        try:
            send_and_wait("NODE_C1", op)
            self.cancel_chute_auto_close(side_raw)
            self.send_resp(req, "OK", "0", {"side": side_raw, "closed": True})
        except Exception as exc:
            self.send_resp(req, "INTERNAL_ERROR", str(exc), {"side": side_raw, "closed": False})


def print_help():
    print("=== NODE Test Server ===")
    print("nodes: a, c, c1")
    print("commands:")
    print("  list")
    print("  make f1|f2|f3|f4 left|right")
    print("  a c      -> bottle.on_the_conveyor")
    print("  a m      -> bottle.on_the_conveyor_man")
    print("  a d      -> bottle.drop_one")
    print("  a s      -> sensor.state")
    print("  a r      -> reboot")
    print("  c f1 left|right")
    print("  c f2 left|right")
    print("  c f3 left|right")
    print("  c f4 left|right")
    print("  c s      -> sensor.state")
    print("  c r      -> reboot")
    print("  c1 p     -> bottle.pick")
    print("  c1 g     -> bottle.go_printer")
    print("  c1 o     -> door.open_left")
    print("  c1 c     -> door.close_left")
    print("  c1 or    -> door.open_right")
    print("  c1 cr    -> door.close_right")
    print("  c1 s     -> sensor.state")
    print("  c1 r     -> reboot")
    print("  ping a|c|c1")
    print("  q")


def node_alias(token):
    token = str(token).strip().lower()
    aliases = {"a": "NODE_A", "c": "NODE_C", "c1": "NODE_C1"}
    return aliases.get(token)


def input_loop():
    print_help()
    while True:
        cmd = input("cmd> ").strip().lower()
        if not cmd:
            continue
        if cmd == "q":
            print("quit")
            return
        if cmd == "list":
            clients = REGISTRY.list()
            if not clients:
                print("no clients connected")
            else:
                for node_id, addr in sorted(clients.items()):
                    print("{} -> {}:{}".format(node_id, addr[0], addr[1]))
            continue

        parts = cmd.split()
        if len(parts) < 2:
            print("invalid command")
            continue

        if parts[0] == "make":
            if len(parts) != 3:
                print("use: make f1|f2|f3|f4 left|right")
                continue
            flavor, side = parts[1], parts[2]
            try:
                run_make_cycle(flavor, side)
            except Exception as e:
                print("make cycle error:", e)
            continue

        if parts[0] == "ping":
            target = node_alias(parts[1]) if len(parts) == 2 else None
            if not target:
                print("use: ping a|c|c1")
                continue
            info = REGISTRY.get(target)
            if not info:
                print("{} not connected".format(target))
                continue
            send_msg(info["conn"], make_msg("ping", "ping", {}, dst=target))
            continue

        node_id = node_alias(parts[0])
        if not node_id:
            print("unknown node")
            continue

        if parts[0] == "a":
            if parts[1] == "c":
                send_to(node_id, "bottle.on_the_conveyor")
            elif parts[1] == "m":
                send_to(node_id, "bottle.on_the_conveyor_man")
            elif parts[1] == "d":
                send_to(node_id, "bottle.drop_one")
            elif parts[1] == "s":
                send_to(node_id, "sensor.state")
            elif parts[1] == "r":
                send_to(node_id, "reboot")
            else:
                print("use: a c | a m | a d | a s | a r")
            continue

        if parts[0] == "c":
            if len(parts) == 2 and parts[1] == "s":
                send_to(node_id, "sensor.state")
                continue
            if len(parts) == 2 and parts[1] == "r":
                send_to(node_id, "reboot")
                continue
            if len(parts) != 3:
                print("use: c f1 left|right | c s | c r")
                continue
            flavor, side = parts[1], parts[2]
            if flavor not in ("f1", "f2", "f3", "f4"):
                print("invalid flavor")
                continue
            if side not in ("left", "right"):
                print("invalid side")
                continue
            send_to(node_id, "bottle.fill.{}.{}".format(flavor, side), data=make_fill_payload(flavor))
            continue

        if parts[0] == "c1":
            mapping = {
                "p": "bottle.pick",
                "g": "bottle.go_printer",
                "o": "door.open_left",
                "c": "door.close_left",
                "or": "door.open_right",
                "cr": "door.close_right",
                "s": "sensor.state",
                "r": "reboot",
            }
            op = mapping.get(parts[1])
            if not op:
                print("use: c1 p|g|o|c|or|cr|s|r")
                continue
            send_to(node_id, op)
            continue


def main():
    kiosk = KioskBridge(KIOSK_HOST, KIOSK_PORT)
    kiosk.start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(MAX_CLIENTS)
        print("listening on {}:{} (max_clients={})".format(HOST, PORT, MAX_CLIENTS))
        print("kiosk bridge target {}:{}".format(KIOSK_HOST, KIOSK_PORT))

        accept_thread = threading.Thread(target=accept_loop, args=(server,), daemon=True)
        accept_thread.start()

        input_loop()


if __name__ == "__main__":
    main()

import json
import os
import shutil
import socket
import threading
import time

from monitor import wait_for_status_sequence


HOST = "0.0.0.0"
PORT = 5000
SERVER_ID = "MINIPC-001"
MAX_CLIENTS = 3
PRINT_IMAGE_SOURCE = r"C:\hnb\image\111.png"
PRINT_IMAGE_TARGET_DIR = r"C:\PartnerDRV\Temp"
PRINT_IMAGE_TARGET = os.path.join(PRINT_IMAGE_TARGET_DIR, os.path.basename(PRINT_IMAGE_SOURCE))
PRINTER_STATUS_SEQUENCE = ["Printing", "Finish"]
PRINTER_STATUS_TIMEOUT_S = 120
PRINTER_KEEPALIVE_INTERVAL_S = 1.0
NODE_RECONNECT_WAIT_S = 15


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
                    if old and old["conn"] is not conn:
                        print("replacing existing connection for {}".format(src))
                        try:
                            old["conn"].close()
                        except Exception:
                            pass
                    print("registered {} from {}:{}".format(src, addr[0], addr[1]))

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


def send_to(node_id, op):
    node_id = canonical_node_id(node_id)
    info = REGISTRY.get(node_id)
    if not info:
        raise RuntimeError("{} not connected".format(node_id))
    send_msg(info["conn"], make_msg("req", op, {}, dst=node_id))


def send_and_wait(node_id, op, timeout_s=180):
    after_seq = RESPONSES.snapshot()
    send_to(node_id, op)
    resp = RESPONSES.wait_for(after_seq, node_id, op, timeout_s)
    payload = resp.get("d")
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError("{} {} failed: {}".format(node_id, op, payload.get("msg", "unknown")))
    return resp


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


def run_make_cycle(flavor, side):
    if flavor not in ("f1", "f2", "f3", "f4"):
        raise ValueError("invalid flavor")
    if side not in ("left", "right"):
        raise ValueError("invalid side")

    print("make cycle start:", flavor, side)
    send_and_wait("NODE_A", "bottle.drop_one")
    send_and_wait("NODE_C1", "bottle.go_printer")
    copy_print_image()
    wait_printer_finish()
    wait_node_connected("NODE_C1")
    send_and_wait("NODE_C1", "bottle.pick")
    wait_node_connected("NODE_C")
    send_and_wait("NODE_C", "bottle.fill.{}.{}".format(flavor, side))

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

    print("make cycle done:", flavor, side)


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
            send_to(node_id, "bottle.fill.{}.{}".format(flavor, side))
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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(MAX_CLIENTS)
        print("listening on {}:{} (max_clients={})".format(HOST, PORT, MAX_CLIENTS))

        accept_thread = threading.Thread(target=accept_loop, args=(server,), daemon=True)
        accept_thread.start()

        input_loop()


if __name__ == "__main__":
    main()

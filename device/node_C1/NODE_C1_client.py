import json
import time
import re
import machine

from net_w5500 import W5500Net
from di_pcf8575 import init_di
import di_cfg as cfg
from dc_door import DCDoor
from light_control import light_on, light_off
from steppers import StepperDriver

import netConfig
NET = netConfig.NET

NODE_ID = "NODE-C1"
SERVER_ID = "MINIPC-001"

BOTTLE_LEFT = +1
BOTTLE_RIGHT = -1

CONNECT_TIMEOUT_S = 5.0
CONNECT_RETRY = 3
SOCKET_TIMEOUT_S = 10.0
RECONNECT_WAIT_S = 2
SENSOR_WAIT_TIMEOUT_MS = 5000
SENSOR_POLL_INTERVAL_MS = 100
DOOR_RUN_MS = 5000
DOOR_SAFETY_POLL_MS = 50
DOOR_REOPEN_WAIT_MS = 5000
LEFT_DOOR_DIR_PIN = 0
LEFT_DOOR_EN_PIN = 1
RIGHT_DOOR_DIR_PIN = 2
RIGHT_DOOR_EN_PIN = 3
FILE_SERVER_PORT = 7000
FILE_SERVER_TIMEOUT_S = 0.05
FILE_UPLOAD_CONN_TIMEOUT_S = 2.0
IDLE_HEARTBEAT_S = 3.0


def sleep_ms(ms):
    try:
        time.sleep_ms(ms)
    except Exception:
        time.sleep(ms / 1000.0)


def ticks_ms():
    try:
        return time.ticks_ms()
    except Exception:
        return int(time.time() * 1000)


def ticks_diff(now, start):
    try:
        return time.ticks_diff(now, start)
    except Exception:
        return now - start


def is_timeout_error(e):
    s = str(e).lower()
    return ("timed out" in s) or ("etimedout" in s) or ("errno 110" in s)


def make_msg(t, op, d, src=NODE_ID, dst=SERVER_ID):
    return {"t": t, "from": src, "to": dst, "op": op, "d": d}


def to_wire(msg):
    return (json.dumps(msg) + "\n").encode("utf-8")


def send_msg(sock, msg):
    raw = to_wire(msg)
    sent = 0
    while sent < len(raw):
        n = sock.send(raw[sent:])
        if n is None:
            sent = len(raw)
            break
        if n <= 0:
            raise OSError("send returned 0")
        sent += n
    print("TX:", msg)


def parse_lines(buf, chunk):
    buf += chunk
    lines = []
    while True:
        i = buf.find(b"\n")
        if i < 0:
            break
        line = buf[:i].strip()
        buf = buf[i + 1 :]
        if line:
            lines.append(line)
    return buf, lines


def safe_filename(name):
    name = str(name or "").strip().replace("\\", "/")
    if "/" in name:
        name = name.split("/")[-1]
    if not name:
        raise ValueError("empty filename")
    return name


def handle_file_upload_conn(conn):
    try:
        conn.settimeout(FILE_UPLOAD_CONN_TIMEOUT_S)
    except Exception:
        pass

    header = b""
    while b"\n" not in header:
        chunk = conn.recv(256)
        if not chunk:
            raise ValueError("missing filename header")
        header += chunk

    raw_name, file_data = header.split(b"\n", 1)
    filename = safe_filename(raw_name.decode("utf-8").strip())
    total = len(file_data)

    with open(filename, "wb") as fp:
        if file_data:
            fp.write(file_data)
        while True:
            try:
                chunk = conn.recv(1024)
            except OSError as e:
                if is_timeout_error(e):
                    break
                raise
            if not chunk:
                break
            fp.write(chunk)
            total += len(chunk)

    try:
        conn.send(b"OK %s %d\n" % (filename.encode("utf-8"), total))
    except Exception:
        pass

    print("file saved:", filename, total, "bytes")


def service_file_server(file_server):
    try:
        conn, addr = file_server.accept()
    except OSError as e:
        if is_timeout_error(e):
            return
        raise

    print("file upload connected from {}:{}".format(addr[0], addr[1]))
    try:
        handle_file_upload_conn(conn)
    except Exception as e:
        print("file upload error:", e)
        try:
            conn.send(("ERR %s\n" % str(e)).encode("utf-8"))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def connect_pc(nw):
    host = NET.get("pc_ip", "192.168.3.6")
    port = int(NET.get("pc_port", 5000))
    print("TCP target:", host, port)
    last_err = None
    for i in range(CONNECT_RETRY):
        try:
            sock = nw.make_client(host, port, timeout_s=CONNECT_TIMEOUT_S)
            try:
                sock.settimeout(SOCKET_TIMEOUT_S)
            except Exception:
                pass
            print("TCP connected:", host, port)
            return sock
        except Exception as e:
            last_err = e
            print("CONNECT retry {}/{} fail: {}".format(i + 1, CONNECT_RETRY, e))
            sleep_ms(300)
    raise OSError(last_err)


def monotonic_s():
    try:
        return time.ticks_ms() / 1000.0
    except Exception:
        return time.time()


def step_left(di, bottle_x):
    result, sensor = bottle_x.move(
        distance_mm=300,
        speed_mm_s=500.0,
        direction=BOTTLE_LEFT,
        accel_ratio=0.5,
        di=di,
        stop_sensors="S4-LeftEnd",
    )
    di.scan()
    s4 = di.get_name("S4-LeftEnd")
    return {"result": result, "sensor": sensor, "S4-LeftEnd": s4}

def step_right(di, bottle_x):
    result, sensor = bottle_x.move(
        distance_mm=300,
        speed_mm_s=500.0,
        direction=BOTTLE_RIGHT,
        accel_ratio=0.5,
        di=di,
        stop_sensors="S3-RightEnd",
    )
    di.scan()
    s5 = di.get_name("S5-BottleArrived")
    return {"result": result, "sensor": sensor, "S5-BottleArrived": s5}


def sensor_state(di):
    def sensor_sort_key(sensor):
        name = str(sensor.get("name", ""))
        match = re.match(r"^S(\d+)", name)
        if match:
            return (int(match.group(1)), name)
        return (9999, name)

    di.scan()
    data = []
    for sensor in sorted(cfg.SENSORS, key=sensor_sort_key):
        name = sensor["name"]
        key = str(name).replace("-", "_")
        data.append({"name": key, "value": di.get_name(name)})
    return data

def wait_sensor_on(di, sensor_name, timeout_ms=SENSOR_WAIT_TIMEOUT_MS, poll_ms=SENSOR_POLL_INTERVAL_MS):
    start = ticks_ms()
    while ticks_diff(ticks_ms(), start) < timeout_ms:
        di.scan()
        if di.get_name(sensor_name):
            return True
        sleep_ms(poll_ms)
    return False

def bottle_pick(di, bottle_x):
    data = step_left(di, bottle_x)
    return data

def bottle_go_printer(di, bottle_x):
    data = step_right(di, bottle_x)
    if wait_sensor_on(di, "S5-BottleArrived"):
        data["S5-BottleArrived"] = True
        return data
    data["S5-BottleArrived"] = False
    if not data.get("S5-BottleArrived"):
        raise ValueError("S5-BottleArrived not detected")
    return data


def get_move_mm(msg, default_mm=150):
    data = msg.get("d", {}) or {}
    mm = data.get("mm", default_mm)
    try:
        return float(mm)
    except Exception:
        return float(default_mm)


def get_run_ms(msg, default_ms=DOOR_RUN_MS):
    data = msg.get("d", {}) or {}
    run_ms = data.get("run_ms", default_ms)
    try:
        return int(run_ms)
    except Exception:
        return default_ms


def door_open_left(left_door, run_ms):
    light_on("left")
    left_door.open_door(run_ms=run_ms)
    return {"run_ms": run_ms}


def bottle_standby(bottle_x, mm):
    result, sensor = bottle_x.move(
        distance_mm=mm,
        speed_mm_s=500.0,
        direction=BOTTLE_LEFT,
        accel_ratio=0.5,
    )
    return {"result": result, "sensor": sensor, "mm": mm}


def door_close_left(di, left_door, run_ms):
    return close_door_with_safety(di, left_door, "left", run_ms)


def door_open_right(right_door, run_ms):
    light_on("right")
    right_door.open_door(run_ms=run_ms)
    return {"run_ms": run_ms}


def is_pinch_detected(di):
    di.scan()
    return bool(di.get_name("S1") or di.get_name("S2"))


def close_door_with_safety(di, door, side, run_ms):
    reopen_count = 0

    while True:
        light_off(side)
        start = ticks_ms()
        door.run(DCDoor.DIR_CLOSE)
        try:
            while ticks_diff(ticks_ms(), start) < run_ms:
                if is_pinch_detected(di):
                    door.stop()
                    reopen_count += 1
                    light_on(side)
                    door.open_door(run_ms=run_ms)
                    sleep_ms(DOOR_REOPEN_WAIT_MS)
                    break
                sleep_ms(DOOR_SAFETY_POLL_MS)
            else:
                return {"run_ms": run_ms, "reopen_count": reopen_count}
        finally:
            door.stop()


def door_close_right(di, right_door, run_ms):
    return close_door_with_safety(di, right_door, "right", run_ms)

def handle_req(sock, msg, di, bottle_x, left_door, right_door):
    op = msg.get("op", "")
    src = msg.get("from", SERVER_ID)

    try:
        if op == "sensor.state":
            data = sensor_state(di)
            send_msg(sock, make_msg("resp", op, data, dst=src))
            return
        elif op == "reboot":
            send_msg(sock, make_msg("resp", op, {"status": "rebooting"}, dst=src))
            sleep_ms(100)
            machine.reset()
            return
        elif op == "step.Left_End":
            data = step_left(di, bottle_x)
            ok = True
        elif op == "step.Right_End":
            data = step_right(di, bottle_x)
            ok = True
        elif op == "bottle.pick":
            data = bottle_pick(di, bottle_x)
            ok = True
        elif op == "bottle.go_printer":
            data = bottle_go_printer(di, bottle_x)
            ok = True
        elif op == "bottle.standby":
            data = bottle_standby(bottle_x, get_move_mm(msg))
            ok = True
        elif op == "door.open_left":
            data = door_open_left(left_door, get_run_ms(msg))
            ok = True
        elif op == "door.close_left":
            data = door_close_left(di, left_door, get_run_ms(msg))
            ok = True
        elif op == "door.open_right":
            data = door_open_right(right_door, get_run_ms(msg))
            ok = True
        elif op == "door.close_right":
            data = door_close_right(di, right_door, get_run_ms(msg))
            ok = True
        else:
            ok = False
            data = {"msg": "unsupported op"}

        send_msg(sock, make_msg("resp", op, {"ok": ok, "data": data}, dst=src))
        send_msg(sock, make_msg("evt", "step.done", {"act": op, "ok": ok}, dst=src))
    except Exception as e:
        err = {"ok": False, "msg": str(e)}
        send_msg(sock, make_msg("resp", op, err, dst=src))
        send_msg(sock, make_msg("evt", "error", {"act": op, "msg": str(e)}, dst=src))


def run_once():
    # motion init (from C1_cycle_test.py flow)
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)
    bottle_x = StepperDriver(step_pin=7, dir_pin=6, stroke_per_mm=29)
    left_door = DCDoor(dir_pin=LEFT_DOOR_DIR_PIN, en_pin=LEFT_DOOR_EN_PIN)
    right_door = DCDoor(dir_pin=RIGHT_DOOR_DIR_PIN, en_pin=RIGHT_DOOR_EN_PIN)

    nw = W5500Net(NET)
    nw.bringup(dhcp=False, verbose=False)
    print("ifconfig:", nw.ifconfig())
    nw.print_mac()
    print("pc_ip:", NET.get("pc_ip"))
    print("pc_port:", NET.get("pc_port", 5000))
    print("file_port:", FILE_SERVER_PORT)

    sock = connect_pc(nw)
    buf = b""
    file_server = nw.make_server(FILE_SERVER_PORT, backlog=1, timeout_s=FILE_SERVER_TIMEOUT_S)

    send_msg(sock, make_msg("hello", "hello", {"kind": "stepper", "fw": "1.0"}))
    send_msg(sock, make_msg("evt", "node.status", {"state": "ready"}))
    last_tx_at = monotonic_s()

    try:
        while True:
            service_file_server(file_server)
            try:
                now = monotonic_s()
                if now - last_tx_at >= IDLE_HEARTBEAT_S:
                    send_msg(sock, make_msg("evt", "node.status", {"state": "ready"}))
                    last_tx_at = now

                chunk = sock.recv(2048)
                if not chunk:
                    raise OSError("server closed")
                buf, lines = parse_lines(buf, chunk)
                for line in lines:
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except Exception as e:
                        print("bad json:", e)
                        continue
                    print("RX:", msg)
                    t = msg.get("t")
                    if t == "ping":
                        send_msg(sock, make_msg("pong", "pong", {}, dst=msg.get("from", SERVER_ID)))
                        last_tx_at = monotonic_s()
                    elif t == "req":
                        handle_req(sock, msg, di, bottle_x, left_door, right_door)
                        last_tx_at = monotonic_s()
            except OSError as e:
                if is_timeout_error(e):
                    continue
                raise
    finally:
        try:
            sock.close()
        except Exception:
            pass
        try:
            file_server.close()
        except Exception:
            pass


def main():
    while True:
        try:
            run_once()
        except Exception as e:
            print("loop error:", e)
            sleep_ms(RECONNECT_WAIT_S * 1000)


if __name__ == "__main__":
    main()

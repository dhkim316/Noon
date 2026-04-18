import json
import time
import re
import machine

from net_w5500 import W5500Net
from di_pcf8575 import init_di
import di_cfg as cfg
from dc_gripper import DCBottleGripper
from steppers import StepperDriver
from rgi100_gripper import RGI100Node
from dc_conveyorC import DCConveyor
from C_cycle_test import make_bottle

import netConfig
NET = netConfig.NET

NODE_ID = "NODE_C"
SERVER_ID = "MINIPC-001"

CONNECT_TIMEOUT_S = 5.0
CONNECT_RETRY = 3
SOCKET_TIMEOUT_S = 10.0
RECONNECT_WAIT_S = 2
FILE_SERVER_PORT = 7000
FILE_SERVER_TIMEOUT_S = 0.05
FILE_UPLOAD_CONN_TIMEOUT_S = 2.0
IDLE_HEARTBEAT_S = 3.0


def sleep_ms(ms):
    try:
        time.sleep_ms(ms)
    except Exception:
        time.sleep(ms / 1000.0)


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


def parse_fill_op(op):
    parts = str(op).split(".")
    if len(parts) != 4:
        return None, None
    if parts[0] != "bottle" or parts[1] != "fill":
        return None, None

    flavor = parts[2]
    side = parts[3]

    if flavor not in ("f1", "f2", "f3", "f4"):
        return None, None
    if side not in ("left", "right"):
        return None, None
    return flavor, side


def parse_fill_ms(msg):
    data = msg.get("d", {}) or {}
    fill_ms = data.get("fill_ms")
    if fill_ms is None:
        return {}
    if not isinstance(fill_ms, dict):
        raise ValueError("fill_ms must be an object")

    result = {}
    for pump_name, value in fill_ms.items():
        name = str(pump_name).lower()
        if name not in ("f1", "f2", "f3", "f4"):
            raise ValueError("unsupported fill_ms pump: {}".format(pump_name))
        try:
            ms = int(value)
        except Exception:
            raise ValueError("invalid fill_ms for {}: {}".format(name, value))
        if ms < 0:
            raise ValueError("fill_ms must be >= 0 for {}".format(name))
        result[name] = ms
    return result


def init_instances():
    cap_gripper = RGI100Node()
    conv_left = DCConveyor(14)
    conv_right = DCConveyor(15)
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)
    bottle_x = StepperDriver(step_pin=3, dir_pin=2, stroke_per_mm=29)
    bottle_y = StepperDriver(step_pin=5, dir_pin=4, stroke_per_mm=29)
    bottle_z = StepperDriver(step_pin=1, dir_pin=0, stroke_per_mm=29)
    cap_y = StepperDriver(step_pin=7, dir_pin=6, stroke_per_mm=167)
    bottle_gripper = DCBottleGripper(8, 9)
    return {
        "cap_gripper": cap_gripper,
        "conv_left": conv_left,
        "conv_right": conv_right,
        "di": di,
        "bottle_x": bottle_x,
        "bottle_y": bottle_y,
        "bottle_z": bottle_z,
        "cap_y": cap_y,
        "bottle_gripper": bottle_gripper,
    }


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


def handle_req(sock, msg, instances):
    op = msg.get("op", "")
    src = msg.get("from", SERVER_ID)
    flavor, side = parse_fill_op(op)

    try:
        if op == "sensor.state":
            send_msg(sock, make_msg("resp", op, sensor_state(instances["di"]), dst=src))
            return
        if op == "reboot":
            send_msg(sock, make_msg("resp", op, {"status": "rebooting"}, dst=src))
            sleep_ms(100)
            machine.reset()
            return

        if flavor is None or side is None:
            raise ValueError("unsupported op")

        fill_ms = parse_fill_ms(msg)
        send_msg(sock, make_msg("evt", "node.status", {"state": "busy"}, dst=src))

        make_bottle(
            instances["cap_gripper"],
            instances["conv_left"],
            instances["conv_right"],
            instances["di"],
            instances["bottle_x"],
            instances["bottle_y"],
            instances["bottle_z"],
            instances["cap_y"],
            instances["bottle_gripper"],
            flavor=flavor,
            side=side,
            fill_ms=fill_ms,
        )

        send_msg(
            sock,
            make_msg(
                "resp",
                op,
                {"ok": True, "data": {"flavor": flavor, "side": side, "fill_ms": fill_ms}},
                dst=src,
            ),
        )
        send_msg(sock, make_msg("evt", "node.status", {"state": "ready"}, dst=src))
    except Exception as e:
        send_msg(sock, make_msg("resp", op, {"ok": False, "msg": str(e)}, dst=src))
        send_msg(sock, make_msg("evt", "error", {"act": op, "msg": str(e)}, dst=src))


def run_once():
    instances = init_instances()

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

    send_msg(sock, make_msg("hello", "hello", {"kind": "filler", "fw": "1.0"}))
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
                        handle_req(sock, msg, instances)
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

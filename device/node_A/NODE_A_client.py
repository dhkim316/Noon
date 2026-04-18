import json
import time
import re
import machine

from net_w5500 import W5500Net
from di_pcf8575 import init_di
import di_cfg as cfg
from servo_node import ServoModbusNode
from dc_gripper import DCBottleGripper
from dc_lift import DCLiftMotor
from dc_conveyor import DCConveyor
import A_cycle_test as cycle

import netConfig
NET = netConfig.NET

NODE_ID = "NODE_A"
SERVER_ID = "MINIPC-001"

CONNECT_TIMEOUT_S = 5.0
CONNECT_RETRY = 3
SOCKET_TIMEOUT_S = 10.0
RECONNECT_WAIT_S = 2
IDLE_POLL_MS = 100
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


def send_msg_if_connected(sock, msg):
    if sock is None:
        return
    send_msg(sock, msg)


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


def init_instances():
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)
    servo = ServoModbusNode()
    grip_front = DCBottleGripper(dir_pin=4, en_pin=5)
    grip_rear = DCBottleGripper(dir_pin=6, en_pin=7)
    lift = DCLiftMotor(dir_pin=8, en_pin=9)
    conv = DCConveyor(dir_pin=2, en_pin=3)
    cycle.conv = conv
    return {
        "di": di,
        "servo": servo,
        "grip_front": grip_front,
        "grip_rear": grip_rear,
        "lift": lift,
        "conv": conv,
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


def run_operation(op, instances):
    if op == "bottle.on_the_conveyor":
        cycle.bottle_on_the_conveyor_auto(
            instances["di"],
            instances["servo"],
            instances["grip_front"],
            instances["lift"],
        )
        return True
    elif op == "bottle.on_the_conveyor_man":
        cycle.bottle_on_the_conveyor_manual(
            instances["di"],
            instances["servo"],
            instances["grip_front"],
            instances["lift"],
        )
        return True
    elif op == "bottle.drop_one":
        return cycle.bottle_drop_one(
            instances["di"],
            poll_ms=20,
            wait_on_timeout_ms=42000,
            drop_timeout_ms=7000,
            tail_run_ms=500,
        )
    else:
        raise ValueError("unsupported op")


def handle_req(sock, msg, instances, state):
    op = msg.get("op", "")
    src = msg.get("from", SERVER_ID)

    try:
        if op not in ("bottle.on_the_conveyor", "bottle.on_the_conveyor_man", "bottle.drop_one", "sensor.state", "reboot"):
            raise ValueError("unsupported op")

        if op == "sensor.state":
            send_msg_if_connected(sock, make_msg("resp", op, sensor_state(instances["di"]), dst=src))
            return
        if op == "reboot":
            send_msg_if_connected(sock, make_msg("resp", op, {"status": "rebooting"}, dst=src))
            sleep_ms(100)
            machine.reset()
            return

        state["busy"] = True
        send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "busy"}, dst=src))
        ok = run_operation(op, instances)
        send_msg_if_connected(sock, make_msg("resp", op, {"ok": bool(ok)}, dst=src))
        send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "ready"}, dst=src))
    except Exception as e:
        send_msg_if_connected(sock, make_msg("resp", op, {"ok": False, "msg": str(e)}, dst=src))
        send_msg_if_connected(sock, make_msg("evt", "error", {"act": op, "msg": str(e)}, dst=src))
    finally:
        state["busy"] = False

def handle_idle_s4_trigger(sock, instances, state):
    if state["busy"]:
        return

    di = instances["di"]
    di.scan()
    s4_active = di.get_name("S4")

    if s4_active and not state["s4_latched"]:
        state["s4_latched"] = True
        try:
            state["busy"] = True
            send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "busy"}))
            run_operation("bottle.on_the_conveyor_man", instances)
            send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "ready"}))
        except Exception as e:
            send_msg_if_connected(sock, make_msg("evt", "error", {"act": "bottle.on_the_conveyor_man", "msg": str(e)}))
            send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "ready"}))
        finally:
            state["busy"] = False
    elif not s4_active:
        state["s4_latched"] = False


def handle_idle_s3_trigger(sock, instances, state):
    if state["busy"]:
        return

    di = instances["di"]
    di.scan()
    s3_active = di.get_name("S3")

    if s3_active and not state["s3_latched"]:
        state["s3_latched"] = True
        try:
            state["busy"] = True
            send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "busy"}))
            cycle.bottle_on_the_conveyor_manual_rear(
                instances["di"],
                instances["servo"],
                instances["grip_rear"],
                instances["lift"],
            )
            send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "ready"}))
        except Exception as e:
            send_msg_if_connected(sock, make_msg("evt", "error", {"act": "bottle.on_the_conveyor_manual_rear", "msg": str(e)}))
            send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "ready"}))
        finally:
            state["busy"] = False
    elif not s3_active:
        state["s3_latched"] = False


def run_once():
    instances = init_instances()
    state = {"s4_latched": False, "s3_latched": False, "busy": False}

    nw = W5500Net(NET)
    nw.bringup(dhcp=False, verbose=False)
    print("ifconfig:", nw.ifconfig())
    nw.print_mac()
    print("pc_ip:", NET.get("pc_ip"))
    print("pc_port:", NET.get("pc_port", 5000))
    print("file_port:", FILE_SERVER_PORT)

    sock = None
    buf = b""
    file_server = nw.make_server(FILE_SERVER_PORT, backlog=1, timeout_s=FILE_SERVER_TIMEOUT_S)
    last_tx_at = 0.0

    try:
        while True:
            service_file_server(file_server)

            if sock is None:
                try:
                    sock = connect_pc(nw)
                    buf = b""
                    send_msg(sock, make_msg("hello", "hello", {"kind": "conveyor", "fw": "1.0"}))
                    send_msg(sock, make_msg("evt", "node.status", {"state": "ready"}))
                    last_tx_at = monotonic_s()
                except Exception as e:
                    print("connect pending:", e)
                    handle_idle_s4_trigger(None, instances, state)
                    handle_idle_s3_trigger(None, instances, state)
                    sleep_ms(RECONNECT_WAIT_S * 1000)
                    continue

            try:
                now = monotonic_s()
                if now - last_tx_at >= IDLE_HEARTBEAT_S:
                    send_msg_if_connected(sock, make_msg("evt", "node.status", {"state": "ready"}))
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
                        handle_req(sock, msg, instances, state)
                        last_tx_at = monotonic_s()
                handle_idle_s4_trigger(sock, instances, state)
                handle_idle_s3_trigger(sock, instances, state)
            except OSError as e:
                if is_timeout_error(e):
                    handle_idle_s4_trigger(sock, instances, state)
                    handle_idle_s3_trigger(sock, instances, state)
                    sleep_ms(IDLE_POLL_MS)
                    continue
                try:
                    sock.close()
                except Exception:
                    pass
                sock = None
                raise
    finally:
        try:
            if sock is not None:
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

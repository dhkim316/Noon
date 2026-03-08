import json
import time

from net_w5500 import W5500Net
from di_pcf8575 import init_di
import di_cfg as cfg
from steppers import StepperDriver

import netConfig
NET = netConfig.NET

NODE_ID = "NODE-STEP"
SERVER_ID = "MINIPC-001"

BOTTLE_LEFT = +1
BOTTLE_RIGHT = -1

CONNECT_TIMEOUT_S = 5.0
CONNECT_RETRY = 3
SOCKET_TIMEOUT_S = 2.0
RECONNECT_WAIT_S = 2


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
    s6 = di.get_name("S6-BottleDropped")
    return {"result": result, "sensor": sensor, "S6-BottleDropped": s6}


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


def handle_req(sock, msg, di, bottle_x):
    op = msg.get("op", "")
    src = msg.get("from", SERVER_ID)

    try:
        if op == "step.Left_End":
            data = step_left(di, bottle_x)
            ok = True
        elif op == "step.Right_End":
            data = step_right(di, bottle_x)
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

    nw = W5500Net(NET)
    nw.bringup(dhcp=False, verbose=False)
    print("ifconfig:", nw.ifconfig())
    nw.print_mac()
    print("pc_ip:", NET.get("pc_ip"))
    print("pc_port:", NET.get("pc_port", 5000))

    sock = connect_pc(nw)
    buf = b""

    send_msg(sock, make_msg("hello", "hello", {"kind": "stepper", "fw": "1.0"}))
    send_msg(sock, make_msg("evt", "node.status", {"state": "ready"}))

    try:
        while True:
            try:
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
                    elif t == "req":
                        handle_req(sock, msg, di, bottle_x)
            except OSError as e:
                if is_timeout_error(e):
                    continue
                raise
    finally:
        try:
            sock.close()
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

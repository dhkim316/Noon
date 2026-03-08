import json
import socket
import threading
import time

HOST = "0.0.0.0"
PORT = 5000
SERVER_ID = "MINIPC-001"


def make_msg(t, src, dst, op, d):
    return {"t": t, "from": src, "to": dst, "op": op, "d": d}


def to_wire(msg):
    return (json.dumps(msg) + "\n").encode("utf-8")


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


class Session:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.node_id = "UNKNOWN"
        self.alive = True
        self.lock = threading.Lock()
        self.last_rx = time.time()

    def send(self, msg):
        raw = to_wire(msg)
        with self.lock:
            self.conn.sendall(raw)


SESSIONS = []
SESSIONS_LOCK = threading.Lock()


def handle_message(sess, msg):
    sess.last_rx = time.time()
    t = msg.get("t")
    src = msg.get("from", "UNKNOWN")
    op = msg.get("op", "")
    d = msg.get("d")

    if t == "hello":
        sess.node_id = src
        print("[HELLO]", src, d)
        sess.send(make_msg("resp", SERVER_ID, src, "hello", {"ok": True}))
        return

    if t == "pong":
        print("[PONG ]", src)
        return

    if t == "resp":
        print("[RESP ]", src, op, d)
        return

    if t == "evt":
        print("[EVT  ]", src, op, d)
        return

    print("[RX   ]", src, t, op, d)


def client_loop(sess):
    buf = b""
    try:
        sess.conn.settimeout(1.0)
    except Exception:
        pass
    print("[OPEN ]", sess.addr)
    try:
        while sess.alive:
            try:
                chunk = sess.conn.recv(2048)
                if not chunk:
                    break
                buf, lines = parse_lines(buf, chunk)
                for line in lines:
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except Exception as e:
                        print("[WARN ] bad json from", sess.addr, e)
                        continue
                    handle_message(sess, msg)
            except socket.timeout:
                continue
    except Exception as e:
        print("[ERR  ]", sess.addr, e)
    finally:
        sess.alive = False
        try:
            sess.conn.close()
        except Exception:
            pass
        print("[CLOSE]", sess.addr, "node=", sess.node_id)


def ping_loop():
    while True:
        time.sleep(5)
        dead = []
        with SESSIONS_LOCK:
            for sess in SESSIONS:
                if not sess.alive:
                    dead.append(sess)
                    continue
                try:
                    sess.send(make_msg("ping", SERVER_ID, sess.node_id, "ping", {}))
                except Exception as e:
                    print("[WARN ] ping fail", sess.addr, e)
                    sess.alive = False
                    dead.append(sess)
            for sess in dead:
                if sess in SESSIONS:
                    SESSIONS.remove(sess)


def pick_target():
    with SESSIONS_LOCK:
        for sess in SESSIONS:
            if sess.alive:
                return sess
    return None


def send_step_req(op):
    target = pick_target()
    if target is None:
        print("[WARN ] no connected client")
        return
    req = make_msg("req", SERVER_ID, target.node_id, op, {})
    try:
        target.send(req)
        print("[TX   ]", target.node_id, op)
    except Exception as e:
        print("[WARN ] send fail:", e)


def command_loop():
    print("Commands: l=step.Left_End, r=step.Right_End, q=quit")
    while True:
        try:
            cmd = input("server> ").strip().lower()
        except EOFError:
            print("[INFO ] stdin closed")
            return
        except KeyboardInterrupt:
            return
        if cmd == "q":
            return
        if cmd == "l":
            send_step_req("step.Left_End")
            continue
        if cmd == "r":
            send_step_req("step.Right_End")
            continue
        if cmd == "ls":
            with SESSIONS_LOCK:
                for s in SESSIONS:
                    print("node=", s.node_id, "addr=", s.addr, "alive=", s.alive)
            continue
        print("Unknown command. Use l/r/q/ls")


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(8)
    srv.settimeout(1.0)
    print("NDJSON STEP server listening:", HOST, PORT)

    threading.Thread(target=ping_loop, daemon=True).start()

    stop_event = threading.Event()

    def accept_loop():
        while not stop_event.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            sess = Session(conn, addr)
            with SESSIONS_LOCK:
                SESSIONS.append(sess)
            threading.Thread(target=client_loop, args=(sess,), daemon=True).start()

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()

    try:
        command_loop()
    finally:
        stop_event.set()
        for sess in list(SESSIONS):
            sess.alive = False
            try:
                sess.conn.close()
            except Exception:
                pass
        try:
            srv.close()
        except Exception:
            pass
        print("Server stopped")


if __name__ == "__main__":
    main()

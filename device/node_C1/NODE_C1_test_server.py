import json
import socket
import threading


HOST = "0.0.0.0"
PORT = 5000
SERVER_ID = "MINIPC-001"
NODE_ID = "NODE_C1"


def make_msg(msg_type, op, data, src=SERVER_ID, dst=NODE_ID):
    return {"t": msg_type, "from": src, "to": dst, "op": op, "d": data}


def to_wire(msg):
    return (json.dumps(msg) + "\n").encode("utf-8")


def send_msg(conn, msg):
    conn.sendall(to_wire(msg))
    print("TX:", msg)


def recv_loop(conn, disconnected):
    buf = b""
    while True:
        try:
            chunk = conn.recv(2048)
        except OSError as exc:
            print("recv error:", exc)
            disconnected.set()
            return
        if not chunk:
            print("client disconnected")
            disconnected.set()
            return
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
                print("bad json:", exc, line)
                continue
            print("RX:", msg)


def input_loop(conn, disconnected):
    print("commands: p=bottle.pick, g=bottle.go_printer, o=door.open_left, c=door.close_left, or=door.open_right, cr=door.close_right, q=quit")
    while True:
        if disconnected.is_set():
            print("connection lost; waiting for reconnect")
            return True
        cmd = input("cmd> ").strip().lower()
        if cmd == "p":
            try:
                send_msg(conn, make_msg("req", "bottle.pick", {}))
            except OSError as exc:
                print("send error:", exc)
                disconnected.set()
                return True
        elif cmd == "g":
            try:
                send_msg(conn, make_msg("req", "bottle.go_printer", {}))
            except OSError as exc:
                print("send error:", exc)
                disconnected.set()
                return True
        elif cmd == "o":
            try:
                send_msg(conn, make_msg("req", "door.open_left", {}))
            except OSError as exc:
                print("send error:", exc)
                disconnected.set()
                return True
        elif cmd == "c":
            try:
                send_msg(conn, make_msg("req", "door.close_left", {}))
            except OSError as exc:
                print("send error:", exc)
                disconnected.set()
                return True
        elif cmd == "or":
            try:
                send_msg(conn, make_msg("req", "door.open_right", {}))
            except OSError as exc:
                print("send error:", exc)
                disconnected.set()
                return True
        elif cmd == "cr":
            try:
                send_msg(conn, make_msg("req", "door.close_right", {}))
            except OSError as exc:
                print("send error:", exc)
                disconnected.set()
                return True
        elif cmd == "q":
            print("quit")
            return False
        elif cmd:
            print("unknown command")


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)
        print("listening on {}:{}".format(HOST, PORT))

        while True:
            print("waiting for client...")
            conn, addr = server.accept()
            print("client connected from {}:{}".format(addr[0], addr[1]))

            disconnected = threading.Event()

            with conn:
                rx_thread = threading.Thread(
                    target=recv_loop, args=(conn, disconnected), daemon=True
                )
                rx_thread.start()
                keep_running = input_loop(conn, disconnected)

            if not keep_running:
                break


if __name__ == "__main__":
    main()

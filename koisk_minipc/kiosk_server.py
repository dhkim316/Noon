#!/usr/bin/env python3
import json
import socket
import threading
import time
from typing import Any, Dict, Optional


HOST = "0.0.0.0"
PORT = 8001

class KioskServer:
    def __init__(self) -> None:
        self.conn: Optional[socket.socket] = None
        self.conn_file = None
        self.running = True
        self.pending_lock = threading.Lock()
        self.pending: Dict[str, Dict[str, Any]] = {}
        self.job_seq = 1
        self.req_seq = 1000

    def next_req_id(self) -> str:
        self.req_seq += 1
        return str(self.req_seq)

    def next_job_id(self) -> str:
        job_id = f"J-{time.strftime('%Y%m%d')}-{self.job_seq:04d}"
        self.job_seq += 1
        return job_id

    def send(self, msg: Dict[str, Any]) -> None:
        if not self.conn:
            raise RuntimeError("No active client connection.")
        data = json.dumps(msg, separators=(",", ":")) + "\n"
        self.conn.sendall(data.encode("utf-8"))
        print(f"[TX] {data.strip()}")

    def make_base(self, msg_type: str, msg_id: str, cmd: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "v": 1,
            "type": msg_type,
            "id": msg_id,
            "ts": int(time.time() * 1000),
            "from": "KIOSK-001",
            "cmd": cmd,
            "data": data,
        }

    def receiver_loop(self) -> None:
        assert self.conn_file is not None
        while self.running:
            line = self.conn_file.readline()
            if not line:
                print("[INFO] Client disconnected.")
                self.running = False
                break
            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                print(f"[WARN] Invalid JSON: {line}")
                continue

            print(f"[RX] {line}")
            self.handle_incoming(msg)

    def handle_incoming(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type")
        cmd = msg.get("cmd")

        if msg_type == "resp":
            req_id = str(msg.get("id", ""))
            with self.pending_lock:
                state = self.pending.get(req_id)
                if state:
                    state["resp"] = msg
            return

        if msg_type == "evt" and cmd == "bottle.state":
            data = msg.get("data", {})
            job_id = data.get("job_id")
            state_name = data.get("state")
            if job_id and state_name in ("DONE", "CANCELED", "ERROR"):
                with self.pending_lock:
                    for req_id, state in self.pending.items():
                        if state.get("job_id") == job_id:
                            state["terminal_state"] = state_name
            return

    def wait_for_resp(self, req_id: str, timeout_sec: float = 5.0) -> Dict[str, Any]:
        deadline = time.time() + timeout_sec
        while time.time() < deadline and self.running:
            with self.pending_lock:
                state = self.pending.get(req_id)
                if state and state.get("resp"):
                    return state["resp"]
            time.sleep(0.05)
        raise TimeoutError(f"Timeout waiting response for req id={req_id}")

    def wait_for_terminal_state(self, req_id: str, timeout_sec: float = 10.0) -> str:
        deadline = time.time() + timeout_sec
        while time.time() < deadline and self.running:
            with self.pending_lock:
                state = self.pending.get(req_id)
                if state and state.get("terminal_state"):
                    return str(state["terminal_state"])
            time.sleep(0.05)
        raise TimeoutError(f"Timeout waiting terminal bottle.state for req id={req_id}")

    def run_one_cycle(self) -> None:
        job_id = self.next_job_id()
        start_req_id = self.next_req_id()
        with self.pending_lock:
            self.pending[start_req_id] = {"resp": None, "terminal_state": None, "job_id": job_id}

        start_req = self.make_base(
            msg_type="req",
            msg_id=start_req_id,
            cmd="bottle.start",
            data={"job_id": job_id, "side": "L", "flavor": "f1"},
        )
        self.send(start_req)
        start_resp = self.wait_for_resp(start_req_id)
        code = start_resp.get("result", {}).get("code")
        if code != "OK":
            raise RuntimeError(f"bottle.start failed: {start_resp}")

        terminal_state = self.wait_for_terminal_state(start_req_id)
        if terminal_state == "CANCELED":
            print(f"[CYCLE] Canceled: {job_id}")
            with self.pending_lock:
                self.pending.pop(start_req_id, None)
            return
        if terminal_state == "ERROR":
            with self.pending_lock:
                self.pending.pop(start_req_id, None)
            raise RuntimeError(f"Cycle ended with ERROR state: {job_id}")

        chute_req_id = self.next_req_id()
        with self.pending_lock:
            self.pending[chute_req_id] = {"resp": None, "terminal_state": None, "job_id": job_id}

        chute_req = self.make_base(
            msg_type="req",
            msg_id=chute_req_id,
            cmd="chute.open",
            data={"side": "L", "reason": "user_pickup"},
        )
        self.send(chute_req)
        chute_resp = self.wait_for_resp(chute_req_id)
        chute_ok = chute_resp.get("result", {}).get("code") == "OK"
        opened = chute_resp.get("data", {}).get("opened") is True
        if not chute_ok or not opened:
            raise RuntimeError(f"chute.open failed: {chute_resp}")

        print(f"[CYCLE] Completed: {job_id}")
        with self.pending_lock:
            self.pending.pop(start_req_id, None)
            self.pending.pop(chute_req_id, None)

    def close(self) -> None:
        self.running = False
        try:
            if self.conn_file:
                self.conn_file.close()
        except OSError:
            pass
        try:
            if self.conn:
                self.conn.close()
        except OSError:
            pass


def main() -> None:
    server = KioskServer()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(1)
    print(f"[INFO] Kiosk server listening on {HOST}:{PORT}")
    print("[INFO] Waiting for MiniPC client...")

    conn, addr = sock.accept()
    server.conn = conn
    server.conn_file = conn.makefile("r", encoding="utf-8", newline="\n")
    print(f"[INFO] MiniPC connected: {addr[0]}:{addr[1]}")
    print("[INFO] Press 's' + Enter to run one cycle, 'q' + Enter to quit.")

    recv_thread = threading.Thread(target=server.receiver_loop, daemon=True)
    recv_thread.start()

    try:
        while server.running:
            command = input("> ").strip().lower()
            if command == "s":
                try:
                    server.run_one_cycle()
                except Exception as exc:
                    print(f"[ERROR] {exc}")
            elif command == "q":
                print("[INFO] Shutting down...")
                break
            elif command:
                print("[INFO] Unknown command. Use 's' or 'q'.")
    except (EOFError, KeyboardInterrupt):
        print("\n[INFO] Interrupted.")
    finally:
        server.close()
        try:
            sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import json
import socket
import threading
import time
from typing import Any, Dict


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8001
RETRY_INTERVAL_SEC = 0.3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MiniPC client")
    parser.add_argument("host", nargs="?", default=SERVER_HOST, help=f"Kiosk server host (default: {SERVER_HOST})")
    parser.add_argument("port", nargs="?", type=int, default=SERVER_PORT, help=f"Kiosk server port (default: {SERVER_PORT})")
    return parser.parse_args()


class MiniPCClient:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.sock_file = None
        self.running = True
        self.evt_seq = 2000
        self.send_lock = threading.Lock()

    def close_connection(self) -> None:
        try:
            if self.sock_file:
                self.sock_file.close()
        except OSError:
            pass
        finally:
            self.sock_file = None

        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        finally:
            self.sock = None

    def next_evt_id(self) -> str:
        self.evt_seq += 1
        return f"e-{self.evt_seq}"

    def send(self, msg: Dict[str, Any]) -> None:
        if not self.sock:
            raise RuntimeError("Socket is not connected.")
        payload = json.dumps(msg, separators=(",", ":")) + "\n"
        with self.send_lock:
            self.sock.sendall(payload.encode("utf-8"))
        print(f"[TX] {payload.strip()}")

    def resp(self, req: Dict[str, Any], code: str = "OK", detail: str = "0", data: Dict[str, Any] | None = None) -> None:
        out = {
            "v": 1,
            "type": "resp",
            "id": req.get("id", ""),
            "ts": int(time.time() * 1000),
            "from": "MINIPC-001",
            "cmd": req.get("cmd", ""),
            "result": {"code": code, "detail": detail},
            "data": data or {},
        }
        self.send(out)

    def evt(self, cmd: str, data: Dict[str, Any]) -> None:
        out = {
            "v": 1,
            "type": "evt",
            "id": self.next_evt_id(),
            "ts": int(time.time() * 1000),
            "from": "MINIPC-001",
            "cmd": cmd,
            "data": data,
        }
        self.send(out)

    def wait_for_go_or_stop(self, job_id: str) -> bool:
        while True:
            user_input = input(f"[INPUT] job={job_id} wait for print (go/stop): ").strip().lower()
            if user_input == "go":
                return True
            if user_input == "stop":
                return False
            print("[INFO] Invalid input. Type 'go' or 'stop'.")

    def simulate_bottle_cycle(self, job_id: str, side: str) -> bool:
        self.evt("bottle.stage", {"job_id": job_id, "stage": "START", "side": side})
        time.sleep(0.15)
        self.evt("bottle.printer_arrived", {"job_id": job_id, "arrived": True})
        time.sleep(0.20)
        self.evt("bottle.stage", {"job_id": job_id, "stage": "PRINTER_ARRIVED"})

        go_next = self.wait_for_go_or_stop(job_id)
        if not go_next:
            self.evt(
                "bottle.state",
                {"job_id": job_id, "state": "CANCELED", "message": "stopped_by_operator"},
            )
            print(f"[CYCLE] Stopped by operator. Reset cycle for job={job_id}.")
            return False

        time.sleep(0.15)
        self.evt("bottle.state", {"job_id": job_id, "state": "CREATING"})
        time.sleep(0.20)
        self.evt("bottle.stage", {"job_id": job_id, "stage": "CHUTE_ARRIVED", "side": side})
        time.sleep(0.20)
        self.evt("bottle.state", {"job_id": job_id, "state": "DONE"})
        return True

    def handle_req(self, msg: Dict[str, Any]) -> None:
        cmd = msg.get("cmd")
        data = msg.get("data", {})

        if cmd == "bottle.start":
            job_id = data.get("job_id", "UNKNOWN")
            side = data.get("side", "L")
            self.resp(msg, data={"job_id": job_id, "accepted": True})
            finished = self.simulate_bottle_cycle(job_id, side)
            if not finished:
                return
            return

        if cmd == "chute.open":
            side = data.get("side", "L")
            self.resp(msg, data={"side": side, "opened": True})
            return

        self.resp(msg, code="NOT_SUPPORTED", detail="unsupported command")

    def run(self) -> None:
        try:
            while self.running:
                try:
                    self.sock = socket.create_connection((self.host, self.port), timeout=10)
                    self.sock.settimeout(None)
                    self.sock_file = self.sock.makefile("r", encoding="utf-8", newline="\n")
                    print(f"[INFO] Connected to kiosk server {self.host}:{self.port}")

                    while self.running:
                        line = self.sock_file.readline()
                        if not line:
                            print("[INFO] Server closed connection. Retrying...")
                            break
                        line = line.strip()
                        if not line:
                            continue
                        print(f"[RX] {line}")
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            print(f"[WARN] Invalid JSON: {line}")
                            continue

                        if msg.get("type") == "req":
                            self.handle_req(msg)
                except KeyboardInterrupt:
                    print("[INFO] Client stop: interrupted by user")
                    self.running = False
                except OSError as exc:
                    print(f"[INFO] Connect/read failed: {exc}. Retrying in {RETRY_INTERVAL_SEC:.1f}s...")
                finally:
                    self.close_connection()

                if self.running:
                    time.sleep(RETRY_INTERVAL_SEC)
        finally:
            self.close_connection()


def main() -> None:
    args = parse_args()
    client = MiniPCClient(args.host, args.port)
    client.run()


if __name__ == "__main__":
    main()

import serial
import threading
import re
import time

PORT = "COM4"        # ★ 환경에 맞게 수정
BAUDRATE = 38400
TIMEOUT = 0.1


class RS232Parser:
    PATTERN = re.compile(
        r'@(?P<device>[A-Z]{3})\s*(?P<status>Ready|Printing|Finish)',
        re.IGNORECASE
    )

    def __init__(self):
        self.buffer = ""

    def feed(self, data: str):
        """수신 데이터 스트림 입력"""
        self.buffer += data.replace("\r", "").replace("\n", "")

        events = []
        last_end = 0

        for match in self.PATTERN.finditer(self.buffer):
            events.append({
                "device": match.group("device"),
                "status": match.group("status"),
                "raw": match.group(0)
            })
            last_end = match.end()

        if last_end:
            self.buffer = self.buffer[last_end:]
        elif "@" not in self.buffer:
            self.buffer = ""

        return events


class SerialEventWaiter:
    def __init__(self):
        self._cond = threading.Condition()
        self._events = []

    def handle_event(self, evt):
        with self._cond:
            self._events.append(evt)
            self._cond.notify_all()

    def wait_for_status_sequence(self, statuses, timeout_s, device=None, tick_s=0.5, on_tick=None):
        expected = list(statuses)
        if not expected:
            return []

        matched = []
        index = 0
        start = 0
        end_time = time.time() + timeout_s

        with self._cond:
            while True:
                while start < len(self._events):
                    evt = self._events[start]
                    start += 1

                    if device and evt.get("device", "").upper() != str(device).upper():
                        continue

                    status = evt.get("status")
                    if status != expected[index]:
                        continue

                    matched.append(evt)
                    index += 1
                    if index == len(expected):
                        return matched

                if on_tick:
                    try:
                        on_tick()
                    except Exception:
                        pass

                remaining = end_time - time.time()
                if remaining <= 0:
                    raise TimeoutError(
                        "timeout waiting for status sequence {}".format(" -> ".join(expected))
                    )
                self._cond.wait(min(remaining, tick_s))


class SerialReceiver(threading.Thread):
    def __init__(self, port, baudrate, on_event):
        super().__init__(daemon=True)
        self.ser = serial.Serial(port, baudrate, timeout=TIMEOUT)
        self.parser = RS232Parser()
        self.on_event = on_event
        self.running = True

    def run(self):
        print(f"[INFO] Serial open: {self.ser.port} @ {self.ser.baudrate}")

        while self.running:
            try:
                data = self.ser.read(256)
                if data:
                    text = data.decode(errors="ignore")
                    events = self.parser.feed(text)
                    for e in events:
                        self.on_event(e)
            except Exception as e:
                print("[ERROR]", e)
                break

        self.ser.close()
        print("[INFO] Serial closed")

    def stop(self):
        self.running = False


def wait_for_status_sequence(statuses, timeout_s=60, device=None, port=PORT, baudrate=BAUDRATE, tick_s=0.5, on_tick=None):
    waiter = SerialEventWaiter()
    rx = SerialReceiver(
        port=port,
        baudrate=baudrate,
        on_event=waiter.handle_event
    )
    rx.start()

    try:
        return waiter.wait_for_status_sequence(
            statuses,
            timeout_s,
            device=device,
            tick_s=tick_s,
            on_tick=on_tick,
        )
    finally:
        rx.stop()
        rx.join(timeout=1)


# ---- 이벤트 처리부 ----
def handle_event(evt):
    print(f"[{evt['device']}] {evt['status']}")


# ---- 메인 ----
if __name__ == "__main__":
    rx = SerialReceiver(
        port=PORT,
        baudrate=BAUDRATE,
        on_event=handle_event
    )

    rx.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] 종료 중...")
        rx.stop()

# rs485_port.py (MicroPython)
from machine import UART, Pin
import time

# ===============================
# RS485 전역 설정
# ===============================
RS485 = {
    "uart": 0,

    # RS485 TX / RX 핀
    "tx": 16,
    "rx": 17,

    # 통신 파라미터
    "baud": 115200,
    "parity": "N",     # "N" / "E" / "O"
    "stopbits": 1,
    "timeout_ms": 80,
}

def _parity_from_char(ch):
    # MicroPython: None / 0(even) / 1(odd)
    if ch == "E":
        return 0
    if ch == "O":
        return 1
    return None

class RS485Port:
    def __init__(self):
        self.uart = None

    def init(self):
        cfg = RS485

        self.uart = UART(
            cfg.get("uart", 0),
            baudrate=cfg.get("baud", 115200),
            bits=8,
            parity=_parity_from_char(cfg.get("parity", "N")),
            stop=cfg.get("stopbits", 1),
            tx=Pin(cfg["tx"]),
            rx=Pin(cfg["rx"]),
            timeout=cfg.get("timeout_ms", 80),
        )

    def write(self, data: bytes):
        # RS485는 보통 TX enable → write → flush → RX enable
        n = self.uart.write(data)

        # baudrate에 따라 필요 시 조정
        time.sleep_ms(2)
        return n

    def read(self, nbytes: int = 0):
        if nbytes <= 0:
            return self.uart.read()
        return self.uart.read(nbytes)


def init_rs485():
    port = RS485Port()
    port.init()
    return port

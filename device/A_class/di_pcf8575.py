# di_pcf8575.py (debounce 없음)
from machine import I2C, Pin
import time

class PCF8575DI:
    """
    - PCF8575 16bit input reader
    - invert_mask 적용 후 논리값을 1=active로 통일
    - debounce 없이 즉시 edge 이벤트(rising/falling) 생성
    """

    def __init__(self, i2c_cfg, di_cfg, sensors_cfg):
        self.addr = int(di_cfg["addr"])
        self.invert_mask = int(di_cfg.get("invert_mask", 0)) & 0xFFFF

        self.i2c = I2C(
            int(i2c_cfg["id"]),
            scl=Pin(int(i2c_cfg["scl"])),
            sda=Pin(int(i2c_cfg["sda"])),
            freq=int(i2c_cfg.get("freq", 400_000)),
        )

        # bit -> meta
        self.meta = [{} for _ in range(16)]
        for bit in range(16):
            self.meta[bit] = {"id": bit, "name": f"DI{bit}"}

        for s in sensors_cfg:
            bit = int(s["bit"])
            self.meta[bit] = {
                "id": int(s.get("id", bit)),
                "name": s.get("name", f"DI{bit}"),
            }

        # PCF8575 입력용: 모두 1로 써서 input 상태 유지
        self._write16(0xFFFF)

        self._stable = self._read_logic16()
        self._events = []

    def _write16(self, v):
        self.i2c.writeto(self.addr, bytes([v & 0xFF, (v >> 8) & 0xFF]))

    def _read16(self):
        d = self.i2c.readfrom(self.addr, 2)
        return (d[0] | (d[1] << 8)) & 0xFFFF

    def _read_logic16(self):
        v = self._read16()
        v ^= self.invert_mask
        return v & 0xFFFF

    def scan(self):
        """주기적으로 호출. 변경된 bit를 즉시 이벤트 큐에 push."""
        # now = time.ticks_ms()
        v = self._read_logic16()

        diff = (v ^ self._stable) & 0xFFFF
        if diff == 0:
            return

        for bit in range(16):
            mask = 1 << bit
            if not (diff & mask):
                continue

            newv = 1 if (v & mask) else 0
            if newv:
                self._stable |= mask
                edge = "R"  #rising
            else:
                self._stable &= ~mask
                edge = "F"  #falling

            m = self.meta[bit]
            self._events.append({
                # "ts_ms": now,
                # "bit": bit,
                # "id": m["id"],
                "name": m["name"],
                "value": newv,   # 1=active
                "edge": edge,
            })

    def get_all16(self) -> int:
        return self._stable & 0xFFFF

    def get_bit(self, bit: int) -> int:
        bit = int(bit)
        return 1 if (self._stable & (1 << bit)) else 0

    def get_name(self, name: str) -> int:
        """
        Get DI state by logical name (e.g., "DI0", "DoorSwitch", etc.)
        Returns 1 if active, 0 otherwise. Raises KeyError if not found.
        """
        name = str(name)
        for bit in range(16):
            m = self.meta[bit]
            if m.get("name") == name:
                return 1 if (self._stable & (1 << bit)) else 0
        raise KeyError(f"DI name not found: {name}")

    def pop_events(self):
        ev = self._events
        self._events = []
        return ev


def init_di(i2c_cfg, di_cfg, sensors_cfg):
    return PCF8575DI(i2c_cfg, di_cfg, sensors_cfg)
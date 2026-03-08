# node_servo_modbus.py  (MicroPython on RP2350)
# - RS485 설정은 rs485_port.py의 전역 RS485 사용
# - 단일 서보 노드 전용 (Modbus addr 고정)
# - Modbus RTU: 0x03 read holding, 0x06 write single, 0x10 write multiple

import time
import struct

from rs485_port import init_rs485   # 전역 RS485 사용

import di_cfg as cfg
from di_pcf8575 import init_di


# -----------------------
# Servo definition (node-local)
# -----------------------
ADDR = 1    # 단일 서보 Modbus 주소 (고정)

# -----------------------
# MicroPython compatibility
# -----------------------
try:
    TimeoutError
except NameError:
    class TimeoutError(Exception):
        pass


# -----------------------
# Modbus RTU helpers
# -----------------------
def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
            crc &= 0xFFFF
    return crc


def add_crc(frame_wo_crc: bytes) -> bytes:
    crc = crc16_modbus(frame_wo_crc)
    return frame_wo_crc + struct.pack("<H", crc)


def hexdump(b: bytes) -> str:
    return " ".join("{:02X}".format(x) for x in b)


def s32_to_u16_words(v: int):
    v32 = v & 0xFFFFFFFF
    low = v32 & 0xFFFF
    high = (v32 >> 16) & 0xFFFF
    return low, high


# -----------------------
# Modbus RTU Master
# -----------------------
class ModbusRTUMaster:
    def __init__(self, rs485_port, timeout_ms=80, retries=2):
        self.p = rs485_port
        self.timeout_ms = int(timeout_ms)
        self.retries = int(retries)

    def _read_exact(self, n: int, timeout_ms: int) -> bytes:
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        out = bytearray()
        while len(out) < n and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            chunk = self.p.read(n - len(out))
            if chunk:
                out.extend(chunk)
            else:
                time.sleep_ms(1)
        return bytes(out)

    def _flush_rx(self):
        while True:
            d = self.p.read()
            if not d:
                break

    def _xfer(self, req: bytes, resp_len: int) -> bytes:
        self._flush_rx()
        self.p.write(req)

        # ★ RS485 TX → RX 전환 안정화 (필수)
        time.sleep_us(200)   # 100~500us 권장

        resp = self._read_exact(resp_len, self.timeout_ms)
        if len(resp) != resp_len:
            raise TimeoutError(
                "Short response ({}/{}): {}".format(
                    len(resp), resp_len, hexdump(resp)
                )
            )

        body = resp[:-2]
        crc_rx = struct.unpack("<H", resp[-2:])[0]
        crc_calc = crc16_modbus(body)
        if crc_rx != crc_calc:
            raise ValueError(
                "CRC mismatch rx=0x{:04X} calc=0x{:04X}".format(
                    crc_rx, crc_calc
                )
            )
        return resp

    def read_holding_03(self, addr: int, start_reg: int, count: int):
        req_wo = struct.pack(">BBHH", addr, 0x03,
                             start_reg & 0xFFFF,
                             count & 0xFFFF)
        req = add_crc(req_wo)
        resp_len = 5 + 2 * count

        last_err = None
        for _ in range(self.retries + 1):
            try:
                resp = self._xfer(req, resp_len)
                data = resp[3:-2]
                regs = []
                for i in range(count):
                    regs.append((data[2*i] << 8) | data[2*i+1])
                return regs, req, resp
            except Exception as e:
                last_err = e
                time.sleep_ms(20)
        raise last_err

    def write_single_06(self, addr: int, reg: int, value: int):
        req_wo = struct.pack(">BBHH", addr, 0x06,
                             reg & 0xFFFF,
                             value & 0xFFFF)
        req = add_crc(req_wo)
        resp_len = 8

        last_err = None
        for _ in range(self.retries + 1):
            try:
                resp = self._xfer(req, resp_len)
                if resp[:-2] != req[:-2]:
                    raise ValueError("Echo mismatch")
                return req, resp
            except Exception as e:
                last_err = e
                time.sleep_ms(20)
        raise last_err

    def write_multi_10(self, addr: int, start_reg: int, values):
        qty = len(values)
        payload = bytearray()
        for v in values:
            payload += struct.pack(">H", v & 0xFFFF)

        req_wo = struct.pack(
            ">BBHHB",
            addr, 0x10,
            start_reg & 0xFFFF,
            qty & 0xFFFF,
            qty * 2
        ) + payload

        req = add_crc(req_wo)
        resp_len = 8

        last_err = None
        for _ in range(self.retries + 1):
            try:
                resp = self._xfer(req, resp_len)
                return req, resp
            except Exception as e:
                last_err = e
                time.sleep_ms(20)
        raise last_err

DIR_FORWARD = 1
DIR_REVERSE = 2
# -----------------------
# In-Position 안정화 필터 (100ms)
# -----------------------
class InPositionFilter:
    def __init__(self, hold_ms=100):
        self.hold_ms = int(hold_ms)
        self.on_time = 0
        self.done = False

    def reset(self):
        self.on_time = 0
        self.done = False

    def update(self, inp_on: bool, dt_ms: int) -> bool:
        if self.done:
            return True

        if inp_on:
            self.on_time += dt_ms
            if self.on_time >= self.hold_ms:
                self.done = True
        else:
            self.on_time = 0

        return self.done

# -----------------------
# Servo Modbus Node (single servo)
# -----------------------
class ServoModbusNode:
    def __init__(self):
        self.addr = ADDR

        # ---- Servo ENABLE GPIO (GP0, active-low) ----
        try:
            from machine import Pin
            self._en = Pin(0, Pin.OUT)
            self.enable()   # 기본 ENABLE

            # ---- Homing trigger GPIO (GP1, active-low pulse) ----
            self._home = Pin(1, Pin.OUT)
            self._home.value(1)   # 기본 HIGH (inactive)
        except Exception as e:
            self._en = None
            self._home = None
            print("WARNING: Servo GPIO init failed:", e)

        rs = init_rs485()
        self.mb = ModbusRTUMaster(rs, timeout_ms=80, retries=2)

    # ---- Servo enable / disable ----
    def enable(self):
        if self._en:
            self._en.value(0)   # ENABLE (active-low)
            time.sleep_ms(50)

    def disable(self):
        if self._en:
            self._en.value(1)   # DISABLE
            time.sleep_ms(10)

    # ---- Homing pulse ----
    def home_pulse(self, pulse_ms=100):
        """
        Trigger servo homing.
        GP1: active-low pulse
        enable() is automatically applied.
        """
        if not self._home:
            print("WARNING: Homing GPIO not available")
            return

        self.enable()

        print("[SERVO] Homing pulse start")
        self._home.value(0)
        time.sleep_ms(int(pulse_ms))
        self._home.value(1)
        print("[SERVO] Homing pulse end")

    # ---- public APIs ----
    def read_holding(self, reg: int, count: int = 1):
        try:
            regs, _, _ = self.mb.read_holding_03(self.addr, reg, count)
            return regs
        except TimeoutError as e:
            print("[WARN] read_holding timeout reg", reg)
            return None

    def write_single(self, reg: int, value: int):
        try:
            self.mb.write_single_06(self.addr, reg, value & 0xFFFF)
            return True
        except TimeoutError as e:
            print("[WARN] write_single timeout reg", reg)
            return False

    def write_multi(self, start_reg: int, values):
        try:
            vals = [(int(v) & 0xFFFF) for v in values]
            self.mb.write_multi_10(self.addr, start_reg, vals)
            return True
        except TimeoutError as e:
            print("[WARN] write_multi timeout reg", start_reg)
            return False

    def write32(self, start_reg_low: int, value32: int):
        low, high = s32_to_u16_words(value32)
        return self.write_multi(start_reg_low, [low, high])
    
    # -------------------------------------------------
    # Homing + Position Complete 대기 (S16)
    # -------------------------------------------------
    def homing_wait_inp(
        self,
        di,
        *,
        inp_name="S16",
        hold_ms=100,
        poll_ms=1,
        timeout_ms=15000,
        pulse_ms=100,
    ):
        """
        Homing 실행 후 Position Complete(INP) 안정화 대기

        di          : PCF8575DI instance
        inp_name    : Position Complete DI name (default: S16)
        hold_ms     : INP 안정화 시간 (ms)
        poll_ms     : DI scan 주기 (ms)
        timeout_ms  : Homing 타임아웃
        pulse_ms    : Homing 트리거 펄스 폭
        """

        inp_filter = InPositionFilter(hold_ms=hold_ms)
        inp_filter.reset()

        start_ms = time.ticks_ms()

        # ---- Homing 트리거 ----
        print("[HOME] Homing start")
        self.home_pulse(pulse_ms=pulse_ms)

        # ---- 모니터 루프 ----
        while True:
            di.scan()

            inp = di.get_name(inp_name)   # 1 or 0
            if inp_filter.update(inp, poll_ms):
                print("[HOME] Position Complete (stable {}ms)".format(hold_ms))
                return True

            # ---- 타임아웃 ----
            if time.ticks_diff(time.ticks_ms(), start_ms) > timeout_ms:
                print("[ERR] Homing timeout -> SERVO DISABLE")
                self.disable()
                return False

            time.sleep_ms(poll_ms)

    # -------------------------------------------------
    # Move mm + Position Complete 안정화 (S16, 100ms)
    # -------------------------------------------------
    def move_mm_wait_inp(
        self,
        di,
        mm,
        rpm,
        direction,
        *,
        inp_name="S16",
        hold_ms=100,
        poll_ms=1,
        timeout_ms=10000,
        raw_per_mm=820.0,
    ):
        """
        mm          : 이동 거리 (mm)
        rpm         : 속도
        direction   : 1=Forward, 2=Reverse
        di          : PCF8575DI instance
        inp_name    : Position Complete DI name (default: S16)
        hold_ms     : INP 안정화 시간 (ms)
        poll_ms     : DI scan 주기 (ms)
        timeout_ms  : 이동 타임아웃
        raw_per_mm  : RAW pulse per mm
        """

        # ---- 준비 ----
        pos_raw = int(mm * raw_per_mm + 0.5)
        inp_filter = InPositionFilter(hold_ms=hold_ms)
        inp_filter.reset()

        start_ms = time.ticks_ms()

        # ---- 이동 명령 ----
        print("[MOVE] mm =", mm, "rpm =", rpm, "dir =", direction)
        self.enable()

        self.write_single(356, int(rpm))
        time.sleep_ms(20)

        self.write32(357, pos_raw)
        time.sleep_ms(20)

        self.write_single(359, int(direction))
        print("[MOVE] RUN issued")

        # ---- 모니터 루프 ----
        while True:
            di.scan()

            # level 기반 INP 판정
            inp = di.get_name(inp_name)   # 1 or 0
            if inp_filter.update(inp, poll_ms):
                print("[INP] Position Complete (stable {}ms)".format(hold_ms))
                return True

            # 타임아웃
            if time.ticks_diff(time.ticks_ms(), start_ms) > timeout_ms:
                print("[ERR] INP timeout -> SERVO DISABLE")
                self.disable()          # ★ 명시적 정지
                return False

            time.sleep_ms(poll_ms)

# -----------------------
# Self-test
# -----------------------
# -----------------------
# Self-test
# -----------------------
if __name__ == "__main__":
    print("=== Servo Modbus RS485 Self-Test ===")

    # ---- DI / Servo 초기화 ----
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)
    servo = ServoModbusNode()
    print("Servo addr =", servo.addr)

    # ---- 상태 레지스터 확인 (선택) ----
    servo.write_single(341, 1)
    try:
        r = 341
        regs = servo.read_holding(r, 9)
        for i, v in enumerate(regs):
            print("Reg", r + i, "=", v)
    except Exception as e:
        print("READ FAIL:", e)

    # ---- Homing ----
    cmd = input("Enter (h=home, other=skip): ")
    if cmd == "h":
        ok = servo.homing_wait_inp(
            di,
            hold_ms=200,
            timeout_ms=15000,
        )
    print("HOMING result =", ok)
    input("Enter to continue...")

    # ---- 반복 이동 테스트 ----
    while True:
        print("\n--- FORWARD ---")
        ok = servo.move_mm_wait_inp(
            di,
            mm=280,
            rpm=200,
            direction=DIR_FORWARD,
            hold_ms=200,       # INP 안정화
            timeout_ms=10000,
        )
        print("FORWARD result =", ok)

        time.sleep_ms(500)

        print("\n--- REVERSE ---")
        ok = servo.move_mm_wait_inp(
            di,
            mm=280,
            rpm=200,
            direction=DIR_REVERSE,
            hold_ms=200,
            timeout_ms=10000,
        )
        print("REVERSE result =", ok)

        time.sleep_ms(500)


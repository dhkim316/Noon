# node_rgi100.py  (MicroPython on RP2350)
# - RS485 설정은 rs485_port.py의 전역 RS485 사용
# - 단일 RGI-100-22 전용 (addr = 1 고정)
# - Modbus RTU: FC03 / FC06 / FC10
# - 안정화 적용: delay + retry + 관대한 polling
# - Rotation 추가: set/read angle, speed, force

import time
import struct

from rs485_port import init_rs485

# -----------------------
# RGI-100-22 constants
# -----------------------
ADDR = 1
STROKE_MM = 22.0

# Holding Registers (Gripper)
REG_INIT            = 0x0100
REG_FORCE           = 0x0101
REG_POS_REF         = 0x0103
REG_SPEED           = 0x0104

REG_INIT_STATE      = 0x0200
REG_GRIPPER_STATE   = 0x0201
REG_POS_ACTUAL      = 0x0202

# Holding Registers (Rotation)
REG_ROT_ANGLE       = 0x0105   # write: target angle (int16 assumed)
REG_ROT_SPEED       = 0x0107   # write: rotation speed (%)
REG_ROT_FORCE       = 0x0108   # write: rotation force/torque (%)
REG_ROT_ANGLE_FB    = 0x0208   # read : current angle (int16 assumed)

# -----------------------
# MicroPython compatibility
# -----------------------
try:
    TimeoutError
except NameError:
    class TimeoutError(Exception):
        pass

# -----------------------
# Utils
# -----------------------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def mm_to_permille(mm: float) -> int:
    return clamp(int(round((mm / STROKE_MM) * 1000)), 0, 1000)

def permille_to_mm(p: int) -> float:
    return (p / 1000.0) * STROKE_MM

def int16_to_u16(x: int) -> int:
    # signed int16 -> unsigned uint16 (0..65535)
    return struct.unpack(">H", struct.pack(">h", int(x)))[0]

def u16_to_int16(x: int) -> int:
    # unsigned uint16 -> signed int16
    return struct.unpack(">h", struct.pack(">H", int(x) & 0xFFFF))[0]


# -----------------------
# Modbus CRC
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

def add_crc(frame: bytes) -> bytes:
    return frame + struct.pack("<H", crc16_modbus(frame))

# -----------------------
# Modbus RTU Master (stabilized)
# -----------------------
class ModbusRTUMaster:
    def __init__(self, rs485_port, timeout_ms=100, retries=2):
        self.p = rs485_port
        self.timeout_ms = timeout_ms
        self.retries = retries

    def _flush_rx(self):
        while self.p.read():
            pass

    def _read_exact(self, n: int, timeout_ms: int) -> bytes:
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        buf = bytearray()
        while len(buf) < n and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            chunk = self.p.read(n - len(buf))
            if chunk:
                buf.extend(chunk)
            else:
                time.sleep_ms(1)
        return bytes(buf)

    def _xfer(self, req: bytes, resp_len: int) -> bytes:
        last_err = None

        for attempt in range(self.retries + 1):
            try:
                self._flush_rx()
                self.p.write(req)
                time.sleep_ms(3)   # ★ 응답 준비 대기

                resp = self._read_exact(resp_len, self.timeout_ms)
                if len(resp) != resp_len:
                    raise TimeoutError("Short response")

                body = resp[:-2]
                crc_rx = struct.unpack("<H", resp[-2:])[0]
                if crc_rx != crc16_modbus(body):
                    raise ValueError("CRC mismatch")

                return resp

            except Exception as e:
                last_err = e
                time.sleep_ms(10 + attempt * 20)

        raise last_err

    # -------- Modbus functions --------
    def read_holding_03(self, addr: int, start_reg: int, count: int):
        req = add_crc(struct.pack(">BBHH", addr, 0x03, start_reg, count))
        resp = self._xfer(req, 5 + 2 * count)
        data = resp[3:-2]
        return [(data[i] << 8) | data[i + 1] for i in range(0, len(data), 2)]

    def write_single_06(self, addr: int, reg: int, value: int):
        req = add_crc(struct.pack(">BBHH", addr, 0x06, reg, value))
        self._xfer(req, 8)
        time.sleep_ms(5)  # ★ write 후 안정화

# -----------------------
# RGI100 device driver
# -----------------------
class RGI100:
    def __init__(self, mb: ModbusRTUMaster):
        self.mb = mb
        self.addr = ADDR

    # ---- Gripper ----
    def initialize(self, full=False):
        self.mb.write_single_06(self.addr, REG_INIT, 0x00A5 if full else 0x0001)

    def set_force(self, percent: int):
        self.mb.write_single_06(self.addr, REG_FORCE, clamp(percent, 20, 100))

    def set_speed(self, percent: int):
        self.mb.write_single_06(self.addr, REG_SPEED, clamp(percent, 1, 100))

    def set_position_mm(self, mm: float):
        self.mb.write_single_06(self.addr, REG_POS_REF, mm_to_permille(mm))

    def read_position_mm(self) -> float:
        return permille_to_mm(self.mb.read_holding_03(self.addr, REG_POS_ACTUAL, 1)[0])

    def read_init_state(self) -> int:
        return self.mb.read_holding_03(self.addr, REG_INIT_STATE, 1)[0]

    def read_gripper_state(self) -> int:
        return self.mb.read_holding_03(self.addr, REG_GRIPPER_STATE, 1)[0]

    # ---- Rotation ----
    def set_rotation_speed(self, percent: int):
        self.mb.write_single_06(self.addr, REG_ROT_SPEED, clamp(percent, 1, 100))

    def set_rotation_force(self, percent: int):
        self.mb.write_single_06(self.addr, REG_ROT_FORCE, clamp(percent, 20, 100))

    def set_rotation_angle_deg(self, angle_deg: int):
        # 레지스터가 int16로 정의되었다고 가정하고 u16로 변환해 전송
        self.mb.write_single_06(self.addr, REG_ROT_ANGLE, int16_to_u16(angle_deg))

    def read_rotation_angle_deg(self) -> int:
        u16 = self.mb.read_holding_03(self.addr, REG_ROT_ANGLE_FB, 1)[0]
        return u16_to_int16(u16)

# -----------------------
# RGI100 Node wrapper
# -----------------------
# -----------------------
# RGI100 Node wrapper (정확 정의 버전)
# -----------------------

class RGI100Node:

    def __init__(self):
        rs = init_rs485()
        mb = ModbusRTUMaster(rs, timeout_ms=100, retries=2)
        self.dev = RGI100(mb)
        self.addr = ADDR

    # -------------------------------------------------
    # Initialization
    # -------------------------------------------------
    def reset(self, full=True, timeout_s=10.0):
        self.dev.initialize(full)

        t0 = time.ticks_ms()

        while True:
            try:
                if self.dev.read_init_state() == 1:
                    return
            except Exception:
                pass

            if time.ticks_diff(time.ticks_ms(), t0) > int(timeout_s * 1000):
                raise TimeoutError("RGI100 init timeout")

            time.sleep_ms(300)

    # -------------------------------------------------
    # GRIP CONTROL
    # -------------------------------------------------
    def grip_mm(self, mm, force=60, speed=50):
        """
        절대 폭(mm) 기준 그립
        """
        self.dev.set_force(clamp(force, 20, 100))
        self.dev.set_speed(clamp(speed, 1, 100))
        self.dev.set_position_mm(mm)

    def release_mm(self, mm=STROKE_MM, force=50, speed=50):
        """
        개방
        """
        self.grip_mm(mm, force=force, speed=speed)

    def read_grip_mm(self):
        return self.dev.read_position_mm()

    # -------------------------------------------------
    # ROTATION CONTROL
    # -------------------------------------------------
    def read_rot_deg(self):
        return self.dev.read_rotation_angle_deg()

    def rotate_abs(self, target_deg, speed=30, force=50):
        """
        절대각 회전
        """
        self.dev.set_rotation_speed(clamp(speed, 1, 100))
        self.dev.set_rotation_force(clamp(force, 20, 100))
        self.dev.set_rotation_angle_deg(int(target_deg))

    def rotate_rel(self, delta_deg, speed=30, force=50):
        """
        상대각 회전
        CW  = 음수
        CCW = 양수
        """
        cur = self.read_rot_deg()
        target = clamp(cur + int(delta_deg), -32768, 32767)
        self.rotate_abs(target, speed=speed, force=force)
        return cur, target

    # -------------------------------------------------
    # SAFE ROTATE (각도 도달 확인용)
    # -------------------------------------------------
    def rotate_rel_checked(
        self,
        delta_deg,
        speed=30,
        force=50,
        tol_deg=2,
        timeout_ms=1500,
    ):
        """
        토크 리밋으로 못 가면 False 리턴
        """

        cur, target = self.rotate_rel(delta_deg, speed=speed, force=force)

        t0 = time.ticks_ms()

        while True:
            now = self.read_rot_deg()

            if abs(now - target) <= tol_deg:
                return True

            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                # stall → 현재 위치 유지
                self.rotate_abs(now, speed=10, force=force)
                return False

            time.sleep_ms(20)

    # -------------------------------------------------
    # STATUS
    # -------------------------------------------------
    def status(self):
        try:
            return {
                "addr": self.addr,
                "init": self.dev.read_init_state(),
                "grip_state": self.dev.read_gripper_state(),
                "grip_mm": self.dev.read_position_mm(),
                "rot_deg": self.dev.read_rotation_angle_deg(),
            }
        except Exception:
            return {"addr": self.addr, "error": "comm"}
        
if __name__ == "__main__":
    print("=== RGI100 interactive test ===")
    print("Commands:")
    print("  g20   -> grip to 20mm")
    print("  r30   -> release to 30mm")
    print("  c320  -> rotate CW 320 deg")
    print("  cw320 -> rotate CCW 320 deg")
    print("  f50   -> set force 50%")
    print("  q     -> quit")
    print("")

    g = RGI100Node()
    g.reset(full=True)

    current_force = 50
    current_speed = 50
    current_rot_speed = 30
    current_rot_force = 50

    while True:
        try:
            cmd = input("CMD> ").strip()

            if not cmd:
                continue

            # ---- quit ----
            if cmd == "q":
                print("Exit.")
                break

            # ---- set force ----
            if cmd.startswith("f"):
                val = int(cmd[1:])
                current_force = clamp(val, 20, 100)
                g.dev.set_force(current_force)
                g.dev.set_rotation_force(current_force)
                print("Force set to", current_force)
                continue

            # ---- grip absolute ----
            if cmd.startswith("g"):
                mm = float(cmd[1:])
                g.grip_mm(mm, force=current_force, speed=current_speed)
                print("Grip ->", mm, "mm")
                continue

            # ---- release absolute ----
            if cmd.startswith("r"):
                mm = float(cmd[1:])
                g.release_mm(mm, force=current_force, speed=current_speed)
                print("Release ->", mm, "mm")
                continue

            # ---- rotate CCW ----
            if cmd.startswith("a"):
                deg = int(cmd[1:])
                cur, target = g.rotate_rel(+deg,
                                        speed=current_rot_speed,
                                        force=current_rot_force)
                print("Rotate CCW:", cur, "->", target)
                continue
            print("Unknown command")

        except Exception as e:
            print("Error:", e)
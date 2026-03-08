import time
from machine import Pin

# ----------------------------
# Level Hold Filter
# ----------------------------
class LevelHoldFilter:
    def __init__(self, hold_ms):
        self.hold_ms = hold_ms
        self.acc = 0
        self.done = False

    def reset(self):
        self.acc = 0
        self.done = False

    def update(self, level, dt):
        if self.done:
            return True
        if level:
            self.acc += dt
            if self.acc >= self.hold_ms:
                self.done = True
        else:
            self.acc = 0
        return self.done


# ----------------------------
# DC Lift Motor
# ----------------------------
class DCLiftMotor:
    DIR_UP = 0
    DIR_DOWN = 1

    SENSOR_HI  = "S8_lift_hi"
    SENSOR_MID = "S9_lift_mid"
    SENSOR_LO  = "S10_lift_lo"

    def __init__(self, dir_pin, en_pin):
        self.dir = Pin(dir_pin, Pin.OUT)
        self.en  = Pin(en_pin,  Pin.OUT)
        self.stop()

    # ---- low-level ----
    def run(self, direction):
        self.dir.value(1 if direction else 0)
        self.en.value(0)     # ON (active-low)

    def stop(self):
        self.en.value(1)     # OFF

    # ---- high-level move ----
    def move_to_sensor(
        self,
        di,
        *,
        direction,
        target_sensor,
        hold_ms=50,
        poll_ms=1,
        timeout_ms=5000,
    ):
        filt = LevelHoldFilter(hold_ms)
        filt.reset()

        start = time.ticks_ms()
        self.run(direction)

        while True:
            di.scan()
            level = di.get_name(target_sensor)

            if filt.update(level, poll_ms):
                self.stop()
                print("[LIFT] reached", target_sensor)
                return True

            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                print("[LIFT][ERR] timeout -> STOP")
                self.stop()
                return False

            time.sleep_ms(poll_ms)

    def get_position(self, di):
        """
        return: "hi" | "mid" | "lo" | None
        """
        di.scan()
        hi  = di.get_name(self.SENSOR_HI)
        mid = di.get_name(self.SENSOR_MID)
        lo  = di.get_name(self.SENSOR_LO)

        if hi and not mid and not lo:
            return "hi"
        if mid and not hi and not lo:
            return "mid"
        if lo and not hi and not mid:
            return "lo"

        # 이상 상태 (2개 이상 ON or 전부 OFF)
        return None

    # ---- semantic APIs ----
    def move_hi(self, di, **kw):
        pos = self.get_position(di)
        if pos == "hi":
            print("[LIFT] already at HI")
            return True
        return self.move_to_sensor(
            di,
            direction=self.DIR_UP,
            target_sensor=self.SENSOR_HI,
            **kw
        )

    def move_lo(self, di, **kw):
        pos = self.get_position(di)
        if pos == "lo":
            print("[LIFT] already at LO")
            return True
        return self.move_to_sensor(
            di,
            direction=self.DIR_DOWN,
            target_sensor=self.SENSOR_LO,
            **kw
        )

    def move_mid(self, di, **kw):
        pos = self.get_position(di)

        if pos == "mid":
            print("[LIFT] already at MID")
            return True

        if pos == "lo":
            direction = self.DIR_UP
        elif pos == "hi":
            direction = self.DIR_DOWN
        else:
            print("[LIFT][ERR] unknown position, cannot move to MID")
            self.stop()
            return False

        return self.move_to_sensor(
            di,
            direction=direction,
            target_sensor=self.SENSOR_MID,
            **kw
        )

# ----------------------------
# Manual Test
# ----------------------------
if __name__ == "__main__":
    print("=== DC Lift Motor Test ===")
    print(" h : move HI")
    print(" m : move MID")
    print(" l : move LO")
    print(" s : stop")
    print(" q : quit")
    print("--------------------------")

    # 실제 핀 번호로 수정
    DIR_PIN = 8
    EN_PIN  = 9

    # DI 초기화
    import di_cfg as cfg
    from di_pcf8575 import init_di
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)

    lift = DCLiftMotor(DIR_PIN, EN_PIN)
    print("[INIT] Lift ready (STOP)")

    while True:
        cmd = input("cmd> ").strip().lower()

        if cmd == "h":
            lift.move_hi(di)

        elif cmd == "m":
            lift.move_mid(di)

        elif cmd == "l":
            lift.move_lo(di)

        elif cmd == "s":
            lift.stop()
            print("[CMD] STOP")

        elif cmd == "q":
            lift.stop()
            print("[EXIT]")
            break

        else:
            print("Use h / m / l / s / q")

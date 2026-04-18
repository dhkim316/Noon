import time
from machine import Pin
class DCConveyor:
    # DIR_GRIP = 0
    # DIR_RELEASE = 1
    DIR_GRIP = 1
    DIR_RELEASE = 0

    def __init__(self, en_pin):
        self.en  = Pin(en_pin,  Pin.OUT)
        self.stop()

    def run(self):
        self.en.value(0)     # 모터 ON

    def stop(self):
        self.en.value(1)     # 모터 OFF

    def go(
        self,
        di,
        *,
        sensor_name=None,
        hold_ms=10,
        poll_ms=2,
        timeout_ms=10000,
    ):
        filt = LevelHoldFilter(hold_ms)
        filt.reset()

        start = time.ticks_ms()
        self.run()

        use_sensor = (di is not None) and (sensor_name is not None)

        while True:

            # -------------------------------
            # SENSOR MODE (기존 동작)
            # -------------------------------
            if use_sensor:
                di.scan()
                level = di.get_name(sensor_name)

                if filt.update(level, poll_ms):
                    self.stop()
                    print("[CONV] Bottle stopped (sensor)")
                    return True

            # -------------------------------
            # TIME MODE (fallback)
            # -------------------------------
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                self.stop()
                if use_sensor:
                    print("[CONV][ERR] timeout -> STOP")
                    return False
                else:
                    print("[CONV] done (time mode)")
                    return True

            time.sleep_ms(poll_ms)

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
# Simple manual test
# ----------------------------
if __name__ == "__main__":
    print("=== C class conv Manual Test ===")
    print(" l : left go")
    print(" r : right go")
    print(" s : stop")
    print(" q : quit")
    print("-------------------------------")

    # ---- 핀 번호는 실제 보드에 맞게 수정 ----

    LEFT_EN_PIN = 14
    RIGHT_EN_PIN = 15

    # ---- DI 초기화 ----
    try:
        import di_cfg as cfg
        from di_pcf8575 import init_di
        di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)
        print("[INIT] DI ready")
    except Exception as e:
        di = None
        print("[WARN] DI not available:", e)

    conv_left = DCConveyor(LEFT_EN_PIN)
    conv_right = DCConveyor(RIGHT_EN_PIN)

    while True:
        cmd = input("cmd> ").strip().lower()

        if cmd == "l":
            if not di:
                print("[ERR] DI not initialized")
                continue
            print("[CMD] Left Go")
            conv_left.go(di, sensor_name="S9_left_bottle", timeout_ms=7000)
        elif cmd == "r":
            if not di:
                print("[ERR] DI not initialized")
                continue
            print("[CMD] Right Go")
            conv_right.go(di, sensor_name="S10_right_bottle", timeout_ms=7000)
        elif cmd == "s":
            print("[CMD] STOP")
            conv_left.stop()
            conv_right.stop()

        elif cmd == "q":
            print("[EXIT] quit")
            conv_left.stop()
            conv_right.stop()
            break

        else:
            print("Unknown command. Use l / r / s / q")

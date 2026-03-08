import time
from machine import Pin
class DCBottleGripper:
    # DIR_GRIP = 0
    # DIR_RELEASE = 1
    DIR_GRIP = 1
    DIR_RELEASE = 0

    def __init__(self, dir_pin, en_pin):

        self.dir = Pin(dir_pin, Pin.OUT)
        self.en  = Pin(en_pin,  Pin.OUT)

        self.stop()

    def run(self, direction):
        self.dir.value(1 if direction else 0)
        self.en.value(0)     # 모터 ON

    def stop(self):
        self.en.value(1)     # 모터 OFF

    def hold_bottle(
        self,
        di,
        *,
        sensor_name=None,
        hold_ms=50,
        poll_ms=1,
        timeout_ms=10000,
    ):
        filt = LevelHoldFilter(hold_ms)
        filt.reset()

        start = time.ticks_ms()
        self.run(self.DIR_GRIP)

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
                    print("[GRIP] Bottle gripped (sensor)")
                    return True

            # -------------------------------
            # TIME MODE (fallback)
            # -------------------------------
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                self.stop()
                if use_sensor:
                    print("[GRIP][ERR] timeout -> STOP")
                    return False
                else:
                    print("[GRIP] done (time mode)")
                    return True

            time.sleep_ms(poll_ms)

    def release_bottle(
        self,
        di,
        *,
        sensor_name=None,
        hold_ms=50,
        poll_ms=1,
        timeout_ms=10000,
    ):
        filt = LevelHoldFilter(hold_ms)
        filt.reset()

        start = time.ticks_ms()
        self.run(self.DIR_RELEASE)

        use_sensor = (di is not None) and (sensor_name is not None)

        while True:

            # SENSOR MODE
            if use_sensor:
                di.scan()
                level = di.get_name(sensor_name)

                if filt.update(level, poll_ms):
                    self.stop()
                    print("[RELEASE] Bottle released (sensor)")
                    return True

            # TIME MODE
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                self.stop()
                if use_sensor:
                    print("[RELEASE][ERR] timeout -> STOP")
                    return False
                else:
                    print("[RELEASE] done (time mode)")
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
    print("=== DC Bottle Gripper Manual Test ===")
    print(" g : grip")
    print(" r : release")
    print(" s : stop")
    print(" q : quit")
    print("-------------------------------")

    # ---- 핀 번호는 실제 보드에 맞게 수정 ----
    
    DIR_PIN = 8  
    EN_PIN  = 9

    # ---- DI 초기화 ----
    try:
        import di_cfg as cfg
        from di_pcf8575 import init_di
        di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)
        print("[INIT] DI ready")
    except Exception as e:
        di = None
        print("[WARN] DI not available:", e)

    gripper = DCBottleGripper(DIR_PIN, EN_PIN)
    print("[INIT] Gripper ready (STOP state)")

    while True:
        cmd = input("cmd> ").strip().lower()

        if cmd == "g":
            if not di:
                print("[ERR] DI not initialized")
                continue
            print("[CMD] GRIP")
            # gripper.hold_bottle(di)
            gripper.hold_bottle(di, sensor_name="S11",timeout_ms=7000)
            # gripper.hold_bottle(None,timeout_ms=3000)
        elif cmd == "r":
            if not di:
                print("[ERR] DI not initialized")
                continue
            print("[CMD] RELEASE")
            # gripper.release_bottle(di)
            # gripper.release_bottle(di, sensor_name="S10",timeout_ms=7000)
            gripper.release_bottle(None, timeout_ms=1200)
        elif cmd == "s":
            print("[CMD] STOP")
            gripper.stop()

        elif cmd == "q":
            print("[EXIT] quit")
            gripper.stop()
            break

        else:
            print("Unknown command. Use g / r / s / q")

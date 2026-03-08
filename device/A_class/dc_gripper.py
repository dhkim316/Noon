import time
from machine import Pin
class DCBottleGripper:
    DIR_GRIP = 0
    DIR_RELEASE = 1

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
        sensor_name=None,      # 기본 None
        hold_ms=50,
        poll_ms=1,
        timeout_ms=10000,
    ):
        filt = LevelHoldFilter(hold_ms)
        filt.reset()

        start = time.ticks_ms()
        self.run(self.DIR_GRIP)

        while True:
            di.scan()

            # 🔹 sensor_name이 있을 때만 센서 체크
            if sensor_name is not None:
                level = di.get_name(sensor_name)

                if filt.update(level, poll_ms):
                    self.stop()
                    print("[GRIP] Bottle gripped")
                    return True

            # 🔹 센서가 없으면 timeout까지 계속 동작
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                print("[GRIP][ERR] timeout -> STOP")
                self.stop()
                return False

            time.sleep_ms(poll_ms)

    def release_bottle(
        self,
        di,
        *,
        sensor_name=None,      # 기본 None
        hold_ms=50,
        poll_ms=1,
        timeout_ms=10000,
    ):
        filt = LevelHoldFilter(hold_ms)
        filt.reset()

        start = time.ticks_ms()
        self.run(self.DIR_RELEASE)

        while True:
            di.scan()

            # 🔹 sensor_name이 있을 때만 센서 체크
            if sensor_name is not None:
                level = di.get_name(sensor_name)

                if filt.update(level, poll_ms):
                    self.stop()
                    print("[RELEASE] Bottle released")
                    return True

            # 🔹 센서가 없으면 timeout까지 계속 동작
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                print("[RELEASE][ERR] timeout -> STOP")
                self.stop()
                return False

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
    
    DIR_PIN = 4 #Front Bottle Grip 
    EN_PIN  = 5

    # DIR_PIN = 6 #Rear Bottle Grip 
    # EN_PIN  = 7

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
            # gripper.hold_bottle(di, sensor_name=None)
            # gripper.hold_bottle(di, sensor_name="S13_rear_bottle_grip")

            gripper.hold_bottle(di, sensor_name="S11_front_bottle_grip")

        elif cmd == "r":
            if not di:
                print("[ERR] DI not initialized")
                continue
            print("[CMD] RELEASE")
            # gripper.release_bottle(di, sensor_name=None)
            # gripper.release_bottle(di, sensor_name="S14_rear_bottle_release")
            gripper.release_bottle(di, sensor_name="S12_front_bottle_release")

        elif cmd == "s":
            print("[CMD] STOP")
            gripper.stop()

        elif cmd == "q":
            print("[EXIT] quit")
            gripper.stop()
            break

        else:
            print("Unknown command. Use g / r / s / q")

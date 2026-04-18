import time
from machine import Pin
class DCDoor:
    # 기존 gripper 방향 기준:
    #   hold=0, release=1
    # door 의미로는 open/release, close/hold가 자연스러워서 매핑 반전
    DIR_OPEN = 0
    DIR_CLOSE = 1

    def __init__(self, dir_pin, en_pin):

        self.dir = Pin(dir_pin, Pin.OUT)
        self.en  = Pin(en_pin,  Pin.OUT)

        self.stop()

    def run(self, direction):
        self.dir.value(direction)
        self.en.value(0)     # 모터 ON

    def stop(self):
        self.dir.value(1)
        self.en.value(1)     # 모터 OFF

    def open_door(self, run_ms=3000):
        self.run(self.DIR_OPEN)
        time.sleep_ms(run_ms)
        self.stop()
        print("[OPEN] run_ms={} -> STOP".format(run_ms))
        return True

    def close_door(self, run_ms=3000):
        self.run(self.DIR_CLOSE)
        time.sleep_ms(run_ms)
        self.stop()
        print("[CLOSE] run_ms={} -> STOP".format(run_ms))
        return True

# ----------------------------
# Simple manual test
# ----------------------------
if __name__ == "__main__":
    print("=== DC Door Manual Test ===")
    print(" o / open [ms] : open (default 3000ms)")
    print(" c / close [ms]: close (default 3000ms)")
    print(" s : stop")
    print(" q : quit")
    print("-------------------------------")

    # ---- 핀 번호는 실제 보드에 맞게 수정 ----
    
    DIR_PIN = 0 # Left Door
    EN_PIN  = 1

    # DIR_PIN = 2 # Right Door 
    # EN_PIN  = 3

    door = DCDoor(DIR_PIN, EN_PIN)
    print("[INIT] Door ready (STOP state)")

    while True:
        cmd = input("cmd> ").strip().lower()
        parts = cmd.split()
        action = parts[0] if parts else ""
        run_ms = 5000
        if len(parts) >= 2 and parts[1].isdigit():
            run_ms = int(parts[1])

        if action in ("o", "open"):
            print("[CMD] OPEN")
            door.open_door(run_ms=run_ms)

        elif action in ("c", "close"):
            print("[CMD] CLOSE")
            door.close_door(run_ms=run_ms)

        elif action == "s":
            print("[CMD] STOP")
            door.stop()

        elif action == "q":
            print("[EXIT] quit")
            door.stop()
            break

        else:
            print("Unknown command. Use o / c / s / q")

import time
from machine import Pin

class StableLevelFilter:
    """
    시간 기반 디바운스 필터

    - raw 입력이 hold_ms 동안 안정되면 상태 확정
    - update()는 확정된 안정 상태를 반환
    - rising / falling edge 감지도 가능
    """

    def __init__(self, hold_ms):
        self.hold_ms = hold_ms
        self._stable = 0          # 확정 상태
        self._candidate = 0       # 변화를 시도 중인 상태
        self._t_start = 0         # 변화 시작 시각

    def reset(self, initial=0):
        self._stable = initial
        self._candidate = initial
        self._t_start = time.ticks_ms()

    def update(self, raw):
        now = time.ticks_ms()

        # 변화 없음
        if raw == self._stable:
            self._candidate = raw
            self._t_start = now
            return self._stable

        # 변화 감지
        if raw != self._candidate:
            self._candidate = raw
            self._t_start = now

        # hold 시간 경과 확인
        if time.ticks_diff(now, self._t_start) >= self.hold_ms:
            self._stable = self._candidate

        return self._stable

    def rising(self, raw):
        prev = self._stable
        curr = self.update(raw)
        return prev == 0 and curr == 1

    def falling(self, raw):
        prev = self._stable
        curr = self.update(raw)
        return prev == 1 and curr == 0

    def value(self):
        return self._stable
    
class DCConveyor:
    DIR_FWD = 0     # 컨베이어 전진
    DIR_STOP = 0

    SENSOR_FRONT = "S6_conv_bottle_front"
    SENSOR_REAR  = "S7_conv_bottle_rear"

    def __init__(self, dir_pin, en_pin):
        self.dir = Pin(dir_pin, Pin.OUT)
        self.en  = Pin(en_pin,  Pin.OUT)
        self.stop()

    # ---- low-level ----
    def run(self):
        self.dir.value(self.DIR_FWD)   # 전진
        self.en.value(0)    # ON (active-low)

    def stop(self):
        self.en.value(1)    # OFF

    # -------------------------------------------------
    # Drop exactly ONE bottle
    # -------------------------------------------------
    def drop_one(
        self,
        di,
        *,
        poll_ms=20,
        hold_ms=30,               # 디바운스 시간
        wait_on_timeout_ms=42000,  # S7 ON 확정 대기
        drop_timeout_ms=7000,     # reserved: backward compatibility
        tail_run_ms=500,         # S7 ON 이후 stop 지연 시간
    ):
        print("[CONV] drop_one start")

        self.run()

        filt = StableLevelFilter(hold_ms)
        filt.reset(initial=0)

        # -------------------------
        # Phase 1) S7 안정 ON 대기
        # -------------------------
        t_wait0 = time.ticks_ms()

        while True:
            di.scan()
            raw = 1 if di.get_name(self.SENSOR_REAR) else 0

            if filt.rising(raw):
                print("[CONV] S7 stable ON (bottle arrived)")
                break

            if time.ticks_diff(time.ticks_ms(), t_wait0) > wait_on_timeout_ms:
                print("[CONV][ERR] wait S7 ON timeout -> STOP")
                self.stop()
                return False

            time.sleep_ms(poll_ms)

        # -------------------------
        # Phase 2) S7 ON 이후 추가 구동
        # -------------------------
        t_drop0 = time.ticks_ms()
        print("[CONV] post-detect run {}ms before stop".format(tail_run_ms))

        while True:
            now = time.ticks_ms()

            if time.ticks_diff(now, t_drop0) >= tail_run_ms:
                self.stop()
                print("[CONV] drop complete (post-detect delay done)")
                return True

            time.sleep_ms(poll_ms)

# ----------------------------
# Manual Test
# ----------------------------
if __name__ == "__main__":
    print("=== Conveyor Drop Test ===")
    print(" d : drop one bottle")
    print(" s : stop")
    print(" q : quit")
    print("--------------------------")

    DIR_PIN = 2
    EN_PIN  = 3

    import di_cfg as cfg
    from di_pcf8575 import init_di
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)

    conv = DCConveyor(DIR_PIN, EN_PIN)

    while True:
        cmd = input("cmd> ").strip().lower()

        if cmd == "d":
            # conv.drop_one(di)
            # conv.drop_one(di)
            conv.drop_one(di,
                hold_ms=30,               # 디바운스 시간
                wait_on_timeout_ms=40000,   # S7 ON(병 도착) 대기 최대 시간
                drop_timeout_ms=6000,      # unused
                tail_run_ms=3000,          # S7 ON 이후 stop 지연 시간
            )
        
        elif cmd == "s":
            conv.stop()
            print("[CMD] STOP")

        elif cmd == "q":
            conv.stop()
            print("[EXIT]")
            break

        else:
            print("Use d / s / q")

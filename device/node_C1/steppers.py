from machine import Pin
import time

class StepperDriver:
    def __init__(
        self,
        step_pin: int,
        dir_pin: int,
        # en_pin: int,
        # Full-step 기준 실측값 (기계 물리값)
        stroke_per_mm: float = 0.33  # pulses per mm @ full-step
    ):
        self.step = Pin(step_pin, Pin.OUT, value=1)  # sink 방식, HIGH=OFF
        self.dir  = Pin(dir_pin,  Pin.OUT, value=0)
        # self.en   = Pin(en_pin,   Pin.OUT, value=1) # HIGH = enable

        self.pulse_per_mm = stroke_per_mm
        # Full-step 기준 stroke/mm 저장 (microstep 배율 계산용)
        self.fullstep_stroke_per_mm = stroke_per_mm
        self.pulse_per_rev = 0  # unused (lead_mm removed)
        # 펄스 고정 조건
        self.HIGH_US =270
        self.MIN_LOW_US = 30

    # TODO: 센서 폴링은 이 함수 내부가 아니라 move() 루프에서 주기적으로 처리할 것
    # -----------------------------
    # 저수준 펄스
    # -----------------------------
    def _step_pulse(self, low_us: int):
        self.step.value(0)                 # LOW
        time.sleep_us(low_us)
        self.step.value(1)                 # HIGH
        time.sleep_us(self.HIGH_US)

    # -----------------------------
    # 방향 설정
    # -----------------------------
    def set_dir(self, direction: int):
        # direction: +1 or -1
        self.dir.value(1 if direction > 0 else 0)

    # -----------------------------
    # Enable / Disable
    # -----------------------------
    def enable(self, on: bool = True):
        # self.en.value(1 if on else 0)
        # self.en.value(1)
        pass

    # -----------------------------
    # 마이크로스텝 배율 적용 (Full-step 기준)
    # -----------------------------
    def set_microstep(self, microstep: float):
        """
        microstep: 1, 2, 4, 8, 10, 16, 32 ...
        예) 10 -> 1/10 microstep (2000 pulse/rev)
        """
        self.pulse_per_mm = self.fullstep_stroke_per_mm * microstep
        self.pulse_per_rev = 0  # unused (lead_mm removed)

    # -----------------------------
    # 캘리브레이션용 안전 펄스 (탈조 방지)
    # -----------------------------
    def calib_pulse(self, pulses: int = 300, pulse_us: int = 200, period_us: int = 250):
        """
        pulses   : 출력할 STEP 펄스 개수 (기본 300)
        pulse_us : HIGH 유지 시간 (옵토 고려, 기본 20us)
        period_us: 전체 주기 (기본 2000us = 500Hz, 탈조 방지용 저속)
        """

        self.enable(True)

        for _ in range(pulses):
            self._step_pulse(30)
            time.sleep_ms(10)

    # -----------------------------
    # mm/s → LOW_us 변환
    # -----------------------------
    def speed_to_low_us(self, speed_mm_s: float) -> int:
        pulse_freq = speed_mm_s * self.pulse_per_mm
        period_us = int(1_000_000 / pulse_freq)
        low_us = period_us - self.HIGH_US

        if low_us < self.MIN_LOW_US:
            low_us = self.MIN_LOW_US

        return low_us

    # -----------------------------
    # 메인 이동 함수 (자동 가감속 + optional sensor stop)
    # -----------------------------
    def move(
        self,
        distance_mm: float,
        speed_mm_s: float,
        direction: int = 1,
        accel_ratio: float = 0.2,
        di=None,
        stop_sensors=None,
    ):
        """
        distance_mm : 이동 거리 (mm)
        speed_mm_s  : 목표 속도 (mm/s)
        direction   : +1 / -1
        accel_ratio : 가감속 비율

        di          : PCF8575DI 인스턴스 (옵션)
        stop_sensors: 센서 이름(str) 또는 리스트(["S1","S2"]) (옵션)

        return:
            ("done", None)
            ("sensor_hit", sensor_name)
        """

        # ---- stop_sensors 정규화 ----
        if stop_sensors:
            if isinstance(stop_sensors, str):
                stop_sensors = [stop_sensors]
        else:
            stop_sensors = None  # 명시적으로 None

        self.set_dir(direction)
        self.enable(True)

        total_steps = int(abs(distance_mm) * self.pulse_per_mm)
        print(f"total_steps={total_steps}")

        accel_steps = int(total_steps * accel_ratio)
        if accel_steps * 2 > total_steps:
            accel_steps = total_steps // 2

        # 속도 범위
        start_speed = speed_mm_s * 0.2
        max_speed   = speed_mm_s

        # -----------------------------
        # 내부 함수: pulse (+ optional sensor check)
        # -----------------------------
        def pulse_and_check(low_us):
            self._step_pulse(low_us)

            if not stop_sensors or not di:
                return None

            di.scan()
            for name in stop_sensors:
                if di.get_name(name):
                    return name
            return None

        # ---------- 가속 ----------
        for i in range(accel_steps):
            v = start_speed + (max_speed - start_speed) * i / accel_steps
            low_us = self.speed_to_low_us(v)

            hit = pulse_and_check(low_us)
            if hit:
                return ("sensor_hit", hit)

        # ---------- 등속 ----------
        cruise_steps = total_steps - accel_steps * 2
        low_us = self.speed_to_low_us(max_speed)

        for _ in range(cruise_steps):
            hit = pulse_and_check(low_us)
            if hit:
                return ("sensor_hit", hit)

        # ---------- 감속 ----------
        for i in range(accel_steps, 0, -1):
            v = start_speed + (max_speed - start_speed) * i / accel_steps
            low_us = self.speed_to_low_us(v)

            hit = pulse_and_check(low_us)
            if hit:
                return ("sensor_hit", hit)

        self.enable(False)
        return ("done", None)


# --- Demo code for quick test ---
def _demo():
    # GPIO mapping for quick test
    STEP_PIN = 1
    DIR_PIN  = 0
    # EN_PIN   = 2

    motor = StepperDriver(
        step_pin=STEP_PIN,
        dir_pin=DIR_PIN,
        stroke_per_mm=29  # Full-step 기준 실측값
    )

    # 예: 1/10 microstep 적용 -> stroke/mm ≈ 30
    # motor.set_microstep(10)

    print("StepperDriver demo starting...")
    print("Pins: STEP=GP0, DIR=GP1, EN=GP2")
    print("Move +20mm then -20mm with simple accel/decel")
    time.sleep_ms(500)

    # 1mm 이동 명령
    # motor.move(distance_mm=1.0, speed_mm_s=5.0)
    # motor.set_dir(1)      # 방향 +
    # motor.calib_pulse()   # 기본 300펄스

    while True:
        count = 0
        while count < 3:
            # Forward
            motor.move(distance_mm=50.0, speed_mm_s=200.0, direction=1, accel_ratio=0.1)
            i = input("Enter..")
            if i == 'q' : break
            # Reverse
            motor.move(distance_mm=50.0, speed_mm_s=200.0, direction=-1, accel_ratio=0.1)
            input("Enter..")
            if i == 'q' : break

        print("StepperDriver demo finished.")

def demo_move_with_sensors(motor, di):
    """
    Demo:
      - Forward until S2
      - Then backward until S1
      - 'q' to quit
    """

    import sys
    import select
    import time

    print("=== Stepper Sensor Demo ===")
    print("Forward until S2, then backward until S1")
    print("Press 'q' to quit")

    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)

    try:
        # -----------------------------
        # Forward until S2
        # -----------------------------
        print("[DEMO] FORWARD → waiting for S2")

        result, sensor = motor.move(
            distance_mm=1000,     # 충분히 큰 값 (센서가 멈춤을 결정)
            speed_mm_s=500.0,
            direction=+1,
            accel_ratio=0.5,
            di=di,
            # stop_sensors="S2",    #병 밀기 끝단 센서
            # stop_sensors="S4",      #병 상하 하단 센서
            stop_sensors="S8",      
        )

        if result == "sensor_hit":
            print(f"[DEMO] Sensor hit: {sensor}")

        # 사용자 중단 확인
        if poll.poll(0):
            ch = sys.stdin.read(1)
            if ch == "q":
                raise KeyboardInterrupt

        time.sleep_ms(500)

        # -----------------------------
        # Backward until S1
        # -----------------------------
        print("[DEMO] BACKWARD → waiting for S1")

        result, sensor = motor.move(
            distance_mm=1000,
            speed_mm_s=500.0,
            direction=-1,
            accel_ratio=0.5,
            di=di,
            # stop_sensors="S1",
            # stop_sensors="S3",      #병 상하 상단 센서
            stop_sensors="S7",      #병 상하 상단 센서
        )

        if result == "sensor_hit":
            print(f"[DEMO] Sensor hit: {sensor}")

    except KeyboardInterrupt:
        print("[DEMO] Stopped by user")

    finally:
        motor.enable(False)
        print("[DEMO] Demo finished")

if __name__ == "__main__":
    # _demo()
    import di_cfg as cfg
    from di_pcf8575 import init_di

    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)

    # motor = StepperDriver( #병 밀기
    #     step_pin=1,
    #     dir_pin=0,
    #     stroke_per_mm=29,   # 형님 실측값
    # )

    # motor = StepperDriver(  #병 상하, 정향 -1, 역향 +1 
    #     step_pin=5,
    #     dir_pin=4,
    #     stroke_per_mm=29,   # 형님 실측값
    # )

    motor = StepperDriver( #병 좌우 이송 (물담기용)
        step_pin=3,
        dir_pin=2,
        stroke_per_mm=29,   # 형님 실측값
    )
    # demo_move_with_sensors(motor, di)

    # cap_Y = StepperDriver(step_pin=7, dir_pin=6, stroke_per_mm=49,) #S5, S6 정역 반대임

    while True:
        i = input("go or back?")
        if i == 'g':
            # cap_Y.move(distance_mm=10,speed_mm_s=500.0, direction=-1, accel_ratio=0.5, di=di, stop_sensors="S8",)
            motor.move(distance_mm=1000,speed_mm_s=500.0, direction=+1, accel_ratio=0.5, di=di, stop_sensors="S8",)
        if i == 'b':
            # cap_Y.move(distance_mm=10,speed_mm_s=500.0, direction=+1, accel_ratio=0.5, di=di, stop_sensors="S",)
            motor.move(distance_mm=1000,speed_mm_s=500.0, direction=-1, accel_ratio=0.5, di=di, stop_sensors="S7",)
        if i == 'q': break
        if i == 'c':
            # cap_Y.set_dir(-1)
            # cap_Y.calib_pulse(pulses=500)
            pass
        if i == 'd':
            # cap_Y.set_dir(+1)
            # cap_Y.calib_pulse(pulses=500)
            pass

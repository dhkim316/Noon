# cycle_test_one.py

import time

from di_pcf8575 import init_di
import di_cfg as cfg

from dc_gripper import DCBottleGripper
from steppers import StepperDriver
from rgi100_gripper import RGI100Node
from dc_conveyorC import DCConveyor
from pump_control import pump_control
CAP_UP = +1
CAP_DOWN = -1

BOTTLE_UP = +1
BOTTLE_DOWN = -1

BOTTLE_LEFT = -1
BOTTLE_RIGHT = +1

BOTTLE_FRONT = +1
BOTTLE_REAR = -1

def close_cap(
    cap_gripper,
    cap_Y,
    di,
    turns=3,
    pitch_mm=4.5,
    rot_step_deg=360,
    rot_speed_main=35,
    rot_speed_slow=20,
    rot_force=60,
    z_speed=500.0,
    accel_ratio=0.5,
    CAP_DOWN=CAP_DOWN,
    final_torque_boost=75,
):

    total_steps = int((turns * 360) / rot_step_deg)
    z_step_mm = pitch_mm * (rot_step_deg / 360.0)

    print("[CLOSE] START")

    # 🔥 시작 각도 한번만 읽는다 (중요)
    start_angle = cap_gripper.read_rot_deg()

    for i in range(total_steps):

        if i < 2:
            rspeed = rot_speed_slow
        else:
            rspeed = rot_speed_main

        # 🔥 절대 타겟 (누적 없음)
        target_angle = start_angle - (i + 1) * rot_step_deg

        cap_gripper.rotate_abs(
            target_angle,
            speed=rspeed,
            force=rot_force,
        )

        cap_Y.move(
            distance_mm=z_step_mm,
            speed_mm_s=z_speed,
            direction=CAP_DOWN,
            accel_ratio=accel_ratio,
            di=di,
            stop_sensors=None,
        )

        print("[CLOSE]", i + 1, "/", total_steps)

    # 🔥 마지막 밀착
    final_target = start_angle - total_steps * rot_step_deg - 20

    cap_gripper.rotate_abs(
        final_target,
        speed=15,
        force=final_torque_boost,
    )

    print("[CLOSE] DONE")

def open_cap(
    cap_gripper,
    cap_Y,
    di,
    grip_mm=8,          # 🔹 28mm 캡 기준 기본값
    grip_force=65,
    grip_speed=50,
    turns=3,
    pitch_mm=4.5,
    rot_step_deg=360,
    rot_speed_main=35,
    rot_speed_slow=20,
    rot_force=60,
    z_speed=500.0,
    accel_ratio=0.5,
    CAP_UP=CAP_UP,
):

    total_steps = int((turns * 360) / rot_step_deg)
    z_step_mm = pitch_mm * (rot_step_deg / 360.0)

    print("[OPEN] GRIP")

    # 1️⃣ 그립
    cap_gripper.grip_mm(
        grip_mm,
        force=grip_force,
        speed=grip_speed,
    )

    time.sleep_ms(200)  # 안정화

    print("[OPEN] START ROTATION")

    # 🔹 기준각 한번만 읽음 (중요)
    base_angle = cap_gripper.read_rot_deg()

    for i in range(total_steps):

        # 초기 파단 토크 구간
        if i < 2:
            rspeed = rot_speed_slow
        else:
            rspeed = rot_speed_main

        # 🔥 절대 타겟 계산
        target_angle = base_angle + (i + 1) * rot_step_deg

        cap_gripper.rotate_abs(
            target_angle,
            speed=rspeed,
            force=rot_force,
        )

        # 🔹 Z follower 상승
        cap_Y.move(
            distance_mm=z_step_mm,
            speed_mm_s=z_speed,
            direction=CAP_UP,
            accel_ratio=accel_ratio,
            di=di,
            stop_sensors=None,
        )

        print("[OPEN]", i + 1, "/", total_steps)

    print("[OPEN] DONE (cap still gripped)")


def make_bottle(
    cap_gripper,
    conv_left,
    conv_right,
    di,
    bottle_x,
    bottle_y,
    bottle_z,
    cap_y,
    bottle_gripper,
    flavor="f1",
    side="left",
    fill_ms=None,
):
    def release_bottle():
        bottle_gripper.release_bottle(di, sensor_name="S12_bottle_release", timeout_ms=7000)

    def hold_bottle():
        bottle_gripper.hold_bottle(di, sensor_name="S11_bottle_grip", timeout_ms=7000)

    flavor = str(flavor).lower()
    side = str(side).lower()
    fill_ms = fill_ms or {}

    if flavor not in ("f1", "f2", "f3", "f4"):
        raise ValueError("unsupported flavor: {}".format(flavor))
    if side not in ("left", "right"):
        raise ValueError("unsupported side: {}".format(side))

    def get_fill_ms(name, default_ms):
        value = fill_ms.get(name, default_ms)
        try:
            value = int(value)
        except Exception:
            raise ValueError("invalid fill_ms for {}: {}".format(name, value))
        if value < 0:
            raise ValueError("fill_ms must be >= 0 for {}".format(name))
        return value

    bottle_z.move(distance_mm=400, speed_mm_s=500.0, direction=BOTTLE_REAR, accel_ratio=0.5, di=di, stop_sensors="S1",)
    cap_y.move(distance_mm=100, speed_mm_s=500.0, direction=CAP_DOWN, accel_ratio=0.5, di=di, stop_sensors="S6",)
    cap_gripper.reset(full=True)
    time.sleep(2)
    cap_y.move(distance_mm=100, speed_mm_s=500.0, direction=CAP_UP, accel_ratio=0.5, di=di, stop_sensors="S5",)
    bottle_y.move(distance_mm=700, speed_mm_s=500.0, direction=BOTTLE_DOWN, accel_ratio=0.5, di=di, stop_sensors="S4",)
    bottle_x.move(distance_mm=700, speed_mm_s=500.0, direction=BOTTLE_LEFT, accel_ratio=0.5, di=di, stop_sensors="S7",)
    hold_bottle()
    release_bottle()

    bottle_z.move(distance_mm=400, speed_mm_s=500.0, direction=BOTTLE_FRONT, accel_ratio=0.5, di=di, stop_sensors="S2",)
    bottle_z.move(distance_mm=18, speed_mm_s=500.0, direction=BOTTLE_FRONT, accel_ratio=0.5, di=di, stop_sensors=None,)
    bottle_z.move(distance_mm=40, speed_mm_s=500.0, direction=BOTTLE_REAR, accel_ratio=0.5, di=di, stop_sensors=None,)
    bottle_y.move(distance_mm=700, speed_mm_s=500.0, direction=BOTTLE_UP, accel_ratio=0.5, di=di, stop_sensors="S3",)
    hold_bottle()
    cap_y.move(distance_mm=100, speed_mm_s=500.0, direction=CAP_DOWN, accel_ratio=0.5, di=di, stop_sensors="S6",)
    open_cap(cap_gripper, cap_y, di)
    cap_y.move(distance_mm=100, speed_mm_s=500.0, direction=CAP_UP, accel_ratio=0.5, di=di, stop_sensors="S5",)
    bottle_y.move(distance_mm=200, speed_mm_s=500.0, direction=BOTTLE_DOWN, accel_ratio=0.5, di=di, stop_sensors=None,)

    # f1
    if flavor == "f1":
        bottle_x.move(distance_mm=120-5, speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
        pump_control("f1", get_fill_ms("f1", 1000))
        time.sleep(1)   #wate for water drop

    # f2
    elif flavor == "f2":
        bottle_x.move(distance_mm=215-5, speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
        pump_control("f2", get_fill_ms("f2", 500))
        time.sleep(1)   #wate for water drop
        bottle_x.move(distance_mm=95, speed_mm_s=500.0, direction=BOTTLE_LEFT, accel_ratio=0.5, di=di, stop_sensors="S7",)
        pump_control("f1", get_fill_ms("f1", 2000))
        time.sleep(1)   #wate for water drop

    # f3
    elif flavor == "f3":
        bottle_x.move(distance_mm=235-5, speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
        pump_control("f3", get_fill_ms("f3", 500))
        time.sleep(1)   #wate for water drop
        bottle_x.move(distance_mm=115, speed_mm_s=500.0, direction=BOTTLE_LEFT, accel_ratio=0.5, di=di, stop_sensors="S7",)
        pump_control("f1", get_fill_ms("f1", 2000))
        time.sleep(1)   #wate for water drop

    # f4
    elif flavor == "f4":
        bottle_x.move(distance_mm=255-5, speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
        pump_control("f4", get_fill_ms("f4", 500))
        time.sleep(1)   #wate for water drop
        bottle_x.move(distance_mm=135, speed_mm_s=500.0, direction=BOTTLE_LEFT, accel_ratio=0.5, di=di, stop_sensors="S7",)
        pump_control("f1", get_fill_ms("f1", 2000))
        time.sleep(1)   #wate for water drop

    bottle_x.move(distance_mm=120, speed_mm_s=500.0, direction=BOTTLE_LEFT, accel_ratio=0.5, di=di, stop_sensors="S7",)
    bottle_y.move(distance_mm=200, speed_mm_s=500.0, direction=BOTTLE_UP, accel_ratio=0.5, di=di, stop_sensors=None,)
    cap_y.move(distance_mm=15, speed_mm_s=500.0, direction=CAP_DOWN, accel_ratio=0.5, di=di, stop_sensors=None,)
    close_cap(cap_gripper, cap_y, di)
    cap_gripper.grip_mm(30)
    cap_y.move(distance_mm=100, speed_mm_s=500.0, direction=CAP_UP, accel_ratio=0.5, di=di, stop_sensors="S5",)
    bottle_y.move(distance_mm=200, speed_mm_s=500.0, direction=BOTTLE_DOWN, accel_ratio=0.5, di=di, stop_sensors=None,)

    #left
    if side == "left":
        bottle_x.move(distance_mm=335, speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
        release_bottle()
        conv_left.go(di, sensor_name="S9_left_bottle", timeout_ms=7000)

    #right
    elif side == "right":
        bottle_x.move(distance_mm=515, speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
        release_bottle()
        conv_right.go(di, sensor_name="S10_right_bottle", timeout_ms=7000)

    bottle_z.move(distance_mm=300, speed_mm_s=500.0, direction=BOTTLE_REAR, accel_ratio=0.5, di=di, stop_sensors=None,)
    bottle_z.move(distance_mm=100, speed_mm_s=500.0, direction=BOTTLE_REAR, accel_ratio=0.5, di=di, stop_sensors="S1",)


def test_fill_recipe(flavor="f1", fill_ms=None):
    flavor = str(flavor).lower()
    fill_ms = fill_ms or {}

    if flavor not in ("f1", "f2", "f3", "f4"):
        raise ValueError("unsupported flavor: {}".format(flavor))

    def get_fill_ms(name, default_ms):
        value = fill_ms.get(name, default_ms)
        try:
            value = int(value)
        except Exception:
            raise ValueError("invalid fill_ms for {}: {}".format(name, value))
        if value < 0:
            raise ValueError("fill_ms must be >= 0 for {}".format(name))
        return value

    print("[RECIPE TEST] flavor={}".format(flavor))

    if flavor == "f1":
        ms = get_fill_ms("f1", 1000)
        print("[RECIPE TEST] pump=f1 ms={}".format(ms))
        pump_control("f1", ms)
        time.sleep(1)

    elif flavor == "f2":
        ms_f2 = get_fill_ms("f2", 500)
        ms_f1 = get_fill_ms("f1", 2000)
        print("[RECIPE TEST] pump=f2 ms={}".format(ms_f2))
        pump_control("f2", ms_f2)
        time.sleep(1)
        print("[RECIPE TEST] pump=f1 ms={}".format(ms_f1))
        pump_control("f1", ms_f1)
        time.sleep(1)

    elif flavor == "f3":
        ms_f3 = get_fill_ms("f3", 500)
        ms_f1 = get_fill_ms("f1", 2000)
        print("[RECIPE TEST] pump=f3 ms={}".format(ms_f3))
        pump_control("f3", ms_f3)
        time.sleep(1)
        print("[RECIPE TEST] pump=f1 ms={}".format(ms_f1))
        pump_control("f1", ms_f1)
        time.sleep(1)

    elif flavor == "f4":
        ms_f4 = get_fill_ms("f4", 500)
        ms_f1 = get_fill_ms("f1", 2000)
        print("[RECIPE TEST] pump=f4 ms={}".format(ms_f4))
        pump_control("f4", ms_f4)
        time.sleep(1)
        print("[RECIPE TEST] pump=f1 ms={}".format(ms_f1))
        pump_control("f1", ms_f1)
        time.sleep(1)


def parse_fill_ms_input(text):
    text = str(text or "").strip()
    if not text:
        return {}

    result = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("invalid fill_ms item: {}".format(item))
        name, value = item.split("=", 1)
        name = name.strip().lower()
        if name not in ("f1", "f2", "f3", "f4"):
            raise ValueError("unsupported pump: {}".format(name))
        try:
            ms = int(value.strip())
        except Exception:
            raise ValueError("invalid ms for {}: {}".format(name, value))
        if ms < 0:
            raise ValueError("fill_ms must be >= 0 for {}".format(name))
        result[name] = ms
    return result

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    print("=== INIT ===")

    current_force = 50
    current_speed = 50
    current_rot_speed = 30
    current_rot_force = 50

    cap_gripper = RGI100Node()
    conv_Left = DCConveyor(14)
    conv_Right = DCConveyor(15)
    
    
    # DI
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)

    #병 좌우 이송 (물담기용)
    bottle_X = StepperDriver(step_pin=3, dir_pin=2, stroke_per_mm=29,) #S7, S8
    #병 빈병위로
    bottle_Y = StepperDriver(step_pin=5, dir_pin=4, stroke_per_mm=29,) #S3, S4 정역 반대임
    #병 밀어내기
    bottle_Z = StepperDriver(step_pin=1, dir_pin=0, stroke_per_mm=29,) #S1, S2 
    cap_Y = StepperDriver(step_pin=7, dir_pin=6, stroke_per_mm=167,) #S5, S6 정역 반대임

    # Grippers
    bottle_gripper = DCBottleGripper(8, 9) #dir=8, en=9
    mode = input("mode (cycle|pump) [cycle]: ").strip().lower() or "cycle"
    flavor = input("flavor (f1|f2|f3|f4) [f3]: ").strip().lower() or "f3"

    if mode == "pump":
        fill_ms_text = input("fill_ms (ex: f2=700,f1=1800) []: ").strip()
        fill_ms = parse_fill_ms_input(fill_ms_text)
        test_fill_recipe(flavor=flavor, fill_ms=fill_ms)
    else:
        side = input("side (left|right) [left]: ").strip().lower() or "left"
        make_bottle(
            cap_gripper,
            conv_Left,
            conv_Right,
            di,
            bottle_X,
            bottle_Y,
            bottle_Z,
            cap_Y,
            bottle_gripper,
            flavor=flavor,
            side=side,
        )

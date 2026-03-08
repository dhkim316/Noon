# cycle_test_one.py

import time

from di_pcf8575 import init_di
import di_cfg as cfg

from dc_gripper import DCBottleGripper
from steppers import StepperDriver
from rgi100_gripper import RGI100Node
from dc_conveyorC import DCConveyor

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

    def release_bottle():
        bottle_gripper.release_bottle(None, timeout_ms=1000)
    def hold_bottle():
        bottle_gripper.hold_bottle(di, sensor_name="S11",timeout_ms=10000)

    bottle_Z.move(distance_mm=400,speed_mm_s=500.0, direction=BOTTLE_REAR, accel_ratio=0.5, di=di, stop_sensors="S1",) 
    cap_Y.move(distance_mm=100,speed_mm_s=500.0, direction=CAP_DOWN, accel_ratio=0.5, di=di, stop_sensors="S6",)
    cap_gripper.reset(full=True)
    time.sleep(2)
    cap_Y.move(distance_mm=100,speed_mm_s=500.0, direction=CAP_UP, accel_ratio=0.5, di=di, stop_sensors="S5",)
    bottle_Y.move(distance_mm=700,speed_mm_s=500.0, direction=BOTTLE_DOWN, accel_ratio=0.5, di=di, stop_sensors="S4",)
    bottle_X.move(distance_mm=500,speed_mm_s=500.0, direction=BOTTLE_LEFT, accel_ratio=0.5, di=di, stop_sensors="S7",)
    hold_bottle()
    release_bottle()

    input("Bottle 이송준비완료...")
    bottle_Z.move(distance_mm=400,speed_mm_s=500.0, direction=BOTTLE_FRONT, accel_ratio=0.5, di=di, stop_sensors="S2",) 
    bottle_Z.move(distance_mm=18,speed_mm_s=500.0, direction=BOTTLE_FRONT, accel_ratio=0.5, di=di, stop_sensors=None,)
    bottle_Z.move(distance_mm=40,speed_mm_s=500.0, direction=BOTTLE_REAR, accel_ratio=0.5, di=di, stop_sensors=None,) 
    bottle_Y.move(distance_mm=700,speed_mm_s=500.0, direction=BOTTLE_UP, accel_ratio=0.5, di=di, stop_sensors="S3",)
    hold_bottle()
    cap_Y.move(distance_mm=100,speed_mm_s=500.0, direction=CAP_DOWN, accel_ratio=0.5, di=di, stop_sensors="S6",)
    open_cap(cap_gripper, cap_Y, di)
    cap_Y.move(distance_mm=100,speed_mm_s=500.0, direction=CAP_UP, accel_ratio=0.5, di=di, stop_sensors="S5",)
    bottle_Y.move(distance_mm=200,speed_mm_s=500.0, direction=BOTTLE_DOWN, accel_ratio=0.5, di=di, stop_sensors=None,)
    bottle_X.move(distance_mm=120,speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
    time.sleep(1)   #water
    bottle_X.move(distance_mm=120,speed_mm_s=500.0, direction=BOTTLE_LEFT, accel_ratio=0.5, di=di, stop_sensors="S7",)
    bottle_Y.move(distance_mm=200,speed_mm_s=500.0, direction=BOTTLE_UP, accel_ratio=0.5, di=di, stop_sensors=None,)
    cap_Y.move(distance_mm=15,speed_mm_s=500.0, direction=CAP_DOWN, accel_ratio=0.5, di=di, stop_sensors=None,)
    close_cap(cap_gripper, cap_Y, di)
    cap_gripper.grip_mm(30)
    cap_Y.move(distance_mm=100,speed_mm_s=500.0, direction=CAP_UP, accel_ratio=0.5, di=di, stop_sensors="S5",)
    bottle_Y.move(distance_mm=200,speed_mm_s=500.0, direction=BOTTLE_DOWN, accel_ratio=0.5, di=di, stop_sensors=None,)    
    bottle_X.move(distance_mm=335,speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
    release_bottle()
    conv_Left.go(di, sensor_name="S9",timeout_ms=7000)
    input("Done 1 Cycle...")

    cap_Y.move(distance_mm=100,speed_mm_s=500.0, direction=CAP_UP, accel_ratio=0.5, di=di, stop_sensors="S5",)
    bottle_Y.move(distance_mm=500,speed_mm_s=500.0, direction=BOTTLE_DOWN, accel_ratio=0.5, di=di, stop_sensors="S4",)
    bottle_X.move(distance_mm=335,speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors=None,)
    release_bottle()

    while True:
        i = input("Enter command, bg,br,cr,co,cc: ")
        if i[1:] == 'bg':
            hold_bottle()
        elif i[1:] == 'br':
            release_bottle()
        elif i[1:] == 'cg':   
            mm = float(i[2:])
            cap_gripper.set_grip_abs_mm(mm/2.0, force=current_force, speed=current_speed)
        elif i[1:] == 'co':   #cap open   
            deg = int(i[2:])
            cur, target = cap_gripper.rotate_rel_deg(+deg, speed=current_rot_speed, force=current_rot_force)
            print("Rotate CCW:", cur, "->", target)
        elif i[1:] == 'cc':   #cap close
            deg = int(i[2:])
            cur, target = cap_gripper.rotate_rel_deg(-deg, speed=current_rot_speed, force=current_rot_force)
            print("Rotate CW:", cur, "->", target)
        elif i == 'q':   #cap close
            break

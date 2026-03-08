# cycle_test_one.py

from di_pcf8575 import init_di
import di_cfg as cfg

from servo_node import ServoModbusNode
from dc_gripper import DCBottleGripper
from dc_lift import DCLiftMotor
from dc_conveyor import DCConveyor

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    print("=== INIT ===")

    # DI
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)

    # Servo
    servo = ServoModbusNode()

    # Grippers
    grip_front = DCBottleGripper(dir_pin=4, en_pin=5)
    # Lift
    lift = DCLiftMotor(dir_pin=8, en_pin=9)

    # Conveyor
    conv = DCConveyor(dir_pin=2, en_pin=3)

    while True:
        lift.move_lo(di)
        ok = servo.homing_wait_inp(di, hold_ms=200, timeout_ms=30000,)
        print("HOMING result =", ok)
        input("lift Lo Ready...")

        lift.move_hi(di)
        grip_front.release_bottle(di, sensor_name = "S12_front_bottle_release")
        input("lift Hi Ready...")

        lift.move_mid(di)
        grip_front.hold_bottle(di, sensor_name = "S11_front_bottle_grip")
        input("Lift Mid Ready...")

        lift.move_lo(di)
        input("Lift Lo Ready...")

        while True:
            conv.drop_one(di,
                poll_ms=20,
                wait_on_timeout_ms=35000,   # S7 ON(병 도착) 대기 최대 시간
                drop_timeout_ms=5000,      # S7 ON 이후, S7 OFF + tail 완료 최대 시간
                tail_run_ms=2700,          # S7 OFF 이후 추가 구동 시간
            )
            i = input("Drop one...")
            if i == 'q' : break

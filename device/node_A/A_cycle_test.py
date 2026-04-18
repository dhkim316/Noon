# cycle_test_one.py

from di_pcf8575 import init_di
import di_cfg as cfg

from servo_node import ServoModbusNode, DIR_FORWARD, DIR_REVERSE
from dc_gripper import DCBottleGripper
from dc_lift import DCLiftMotor
from dc_conveyor import DCConveyor
import time
from machine import Pin

LAMP = Pin(15,  Pin.OUT)

def Lamp(state):
    LAMP.value(0 if state else 1)
            
def bottle_drop_one(di, poll_ms=20, wait_on_timeout_ms=42000, drop_timeout_ms=7000,tail_run_ms=500,):
    return conv.drop_one(di,
            poll_ms=poll_ms,
            wait_on_timeout_ms=wait_on_timeout_ms,   # S7 ON(병 도착) 대기 최대 시간
            drop_timeout_ms=drop_timeout_ms,      # unused
            tail_run_ms=tail_run_ms,          # S7 ON 이후 stop 지연 시간
    )
def bottle_on_the_conveyor_manual(di, servo, grip_front, lift):
    # di.scan()
    # level = di.get_name("S1")
    state = True
    while True:
        di.scan()
        level = di.get_name("S1")
        if level: break
        time.sleep_ms(200)
        Lamp(state)
        state = not state

    if level:
        Lamp(False)
        print("Bottle SetUp...")
        lift.move_lo(di)
        ok = servo.homing_wait_inp(di, hold_ms=200, timeout_ms=30000,)
        lift.move_hi(di)
        grip_front.release_bottle(di, sensor_name = "S12_front_bottle_release")
        print("Ready for S2 input...")
        while True:
            di.scan()
            level = di.get_name("S2")
            if level: break
            time.sleep_ms(100)
            Lamp(state)
            state = not state

        Lamp(True)
        lift.move_mid(di)
        grip_front.hold_bottle(di, sensor_name = "S11_front_bottle_grip")
        lift.move_lo(di)
    else:
        print("S1 not detected")

def bottle_on_the_conveyor_manual_rear(di, servo, grip_rear, lift):
    # di.scan()
    # level = di.get_name("S1")
    state = True
    while True:
        di.scan()
        level = di.get_name("S1")
        if level: break
        time.sleep_ms(200)
        Lamp(state)
        state = not state
    if level:
        Lamp(False)
        print("Bottle SetUp...")
        lift.move_lo(di)
        ok = servo.homing_wait_inp(di, hold_ms=200, timeout_ms=30000,)  # 원점이동
        ok = servo.move_mm_wait_inp(di, mm=290, rpm=200, direction=DIR_FORWARD, hold_ms=200, timeout_ms=30000,)
        lift.move_hi(di)
        grip_rear.release_bottle(di, sensor_name = "S14_rear_bottle_release")
        print("Ready for S2 input...")
        while True:
            di.scan()
            level = di.get_name("S2")
            if level: break
            time.sleep_ms(100)
            Lamp(state)
            state = not state

        Lamp(True)
        lift.move_mid(di)
        grip_rear.hold_bottle(di, sensor_name = "S13_rear_bottle_grip")
        lift.move_lo(di)
        ok = servo.homing_wait_inp(di, hold_ms=200, timeout_ms=30000,)
    else:
        print("S1 not detected")

def bottle_on_the_conveyor_auto(di, servo, grip_front, lift):
    lift.move_lo(di)
    ok = servo.homing_wait_inp(di, hold_ms=200, timeout_ms=30000,)
    lift.move_hi(di)
    grip_front.release_bottle(di, sensor_name = "S12_front_bottle_release")
    lift.move_mid(di)
    grip_front.hold_bottle(di, sensor_name = "S11_front_bottle_grip")
    lift.move_lo(di)

def bottle_on_the_conveyor_auto_rear(di, servo, grip_rear, lift):
    lift.move_lo(di)
    ok = servo.homing_wait_inp(di, hold_ms=200, timeout_ms=30000,)  # 원점이동
    ok = servo.move_mm_wait_inp(di, mm=290, rpm=200, direction=DIR_FORWARD, hold_ms=200, timeout_ms=30000,) #goto rear bottle position
    lift.move_hi(di)
    grip_rear.release_bottle(di, sensor_name = "S14_rear_bottle_release")
    lift.move_mid(di)
    grip_rear.hold_bottle(di, sensor_name = "S13_rear_bottle_grip")
    lift.move_lo(di)
    ok = servo.move_mm_wait_inp(di, mm=280, rpm=200, direction=DIR_REVERSE, hold_ms=200, timeout_ms=30000,) #goto standby position
    ok = servo.homing_wait_inp(di, hold_ms=200, timeout_ms=30000,)  #set on home

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    # DI
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)
    # Servo
    servo = ServoModbusNode()
    # Grippers
    # FR_DIR_PIN = 4 #Front Bottle Grip 
    # FR_EN_PIN  = 5
    # RE_DIR_PIN = 6 #Rear Bottle Grip 
    # RE_EN_PIN  = 7

    grip_front = DCBottleGripper(dir_pin=4, en_pin=5)
    grip_rear = DCBottleGripper(dir_pin=6, en_pin=7)

    # Lift
    lift = DCLiftMotor(dir_pin=8, en_pin=9)
    # Conveyor
    conv = DCConveyor(dir_pin=2, en_pin=3)

    while True:
        i = input("manual, auto, drop or quit? ").strip().lower()
        if i == 'd':
            # bottle_drop_one(di, poll_ms=20, wait_on_timeout_ms=42000, drop_timeout_ms=6000,tail_run_ms=3100)
            bottle_drop_one(di, poll_ms=20, wait_on_timeout_ms=42000, drop_timeout_ms=7000,tail_run_ms=500)
        elif i == 'm':  #manual
            # bottle_on_the_conveyor_manual(di, servo, grip_front, lift)
            bottle_on_the_conveyor_manual_rear(di, servo, grip_rear, lift)
        elif i == 'a':  #auto
            # bottle_on_the_conveyor_auto(di, servo, grip_front, lift)
            bottle_on_the_conveyor_auto_rear(di, servo, grip_rear, lift)
        elif i == 'q' : exit()
        else:
            print("Use m / a / d / q")
        time.sleep_ms(10)

# cycle_test_one.py

import time

from di_pcf8575 import init_di
import di_cfg as cfg

from steppers import StepperDriver

BOTTLE_LEFT = +1
BOTTLE_RIGHT = -1

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    print("=== INIT ===")
    
    # DI
    di = init_di(cfg.I2C, cfg.DI, cfg.SENSORS)

    #병 좌우 이송 (프린터로 이송)
    bottle_X = StepperDriver(step_pin=7, dir_pin=6, stroke_per_mm=29,) #S6, S5

    while True:
        i = input("l.left, r.right...")
        if i == 'l':
            bottle_X.move(distance_mm=300,speed_mm_s=500.0, direction=BOTTLE_LEFT, accel_ratio=0.5, di=di, stop_sensors="S4-LeftEnd",)
            di.scan()
            print("S6-BottleDropped:", di.get_name("S6-BottleDropped"))
        if i == 'r':
            bottle_X.move(distance_mm=300,speed_mm_s=500.0, direction=BOTTLE_RIGHT, accel_ratio=0.5, di=di, stop_sensors="S3-RightEnd",)
            di.scan()
            print("S5-BottleArrived:", di.get_name("S5-BottleArrived"))
        time.sleep_ms(10)

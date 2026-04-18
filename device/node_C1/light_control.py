import time
from machine import Pin


LIGHT_GPIO_MAP = {
    "left": 4,
    "right": 5,
}


LIGHTS = {
    name: Pin(pin_no, Pin.OUT, value=1)
    for name, pin_no in LIGHT_GPIO_MAP.items()
}


def sleep_ms(ms):
    try:
        time.sleep_ms(ms)
    except Exception:
        time.sleep(ms / 1000.0)


def set_light(name, on):
    if name not in LIGHTS:
        raise ValueError("unsupported light: {}".format(name))
    pin = LIGHTS[name]
    pin.value(0 if on else 1)
    return pin.value()


def light_on(name):
    return set_light(name, True)


def light_off(name):
    return set_light(name, False)


def light_control(name, on_time=1000):
    if name not in LIGHTS:
        raise ValueError("unsupported light: {}".format(name))

    on_time = int(on_time)
    if on_time < 0:
        raise ValueError("on_time must be >= 0")

    light_on(name)
    print("{} ON (gpio={}, raw=0)".format(name, LIGHT_GPIO_MAP[name]))
    sleep_ms(on_time)
    light_off(name)
    print("{} OFF (gpio={}, raw=1)".format(name, LIGHT_GPIO_MAP[name]))
    return True


def all_off():
    for name in LIGHTS:
        light_off(name)


def print_status():
    for name in ("left", "right"):
        raw = LIGHTS[name].value()
        logical = "ON" if raw == 0 else "OFF"
        print("{}: gpio={} {} (raw={})".format(name, LIGHT_GPIO_MAP[name], logical, raw))


def print_help():
    print("=== Light Control ===")
    print("active-low: ON=0, OFF=1")
    print("mapping: left=GPIO4, right=GPIO5")
    print("commands:")
    print("  left 1000    -> run left light for 1000ms")
    print("  right 1000   -> run right light for 1000ms")
    print("  on left      -> turn left light on")
    print("  off left     -> turn left light off")
    print("  on right     -> turn right light on")
    print("  off right    -> turn right light off")
    print("  status       -> show light states")
    print("  all off      -> turn all lights off")
    print("  q            -> quit")


def main():
    print_help()
    print_status()

    while True:
        cmd = input("cmd> ").strip().lower()
        if not cmd:
            continue

        if cmd == "q":
            all_off()
            print("quit")
            break

        if cmd == "status":
            print_status()
            continue

        if cmd == "all off":
            all_off()
            print("all lights off")
            continue

        parts = cmd.split()

        if len(parts) == 2 and parts[0] in ("on", "off"):
            name = parts[1]
            try:
                raw = set_light(name, parts[0] == "on")
                print("{} {} (raw={})".format(name, parts[0].upper(), raw))
            except ValueError as exc:
                print(exc)
            continue

        if len(parts) == 2:
            name = parts[0]
            try:
                on_time = int(parts[1])
                light_control(name, on_time=on_time)
            except ValueError as exc:
                print(exc)
            continue

        print("invalid command")


if __name__ == "__main__":
    main()

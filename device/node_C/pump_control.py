import time
from machine import Pin


PUMP_GPIO_MAP = {
    "f1": 10,
    "f2": 11,
    "f3": 12,
    "f4": 13,
}


PUMPS = {
    name: Pin(pin_no, Pin.OUT, value=1)
    for name, pin_no in PUMP_GPIO_MAP.items()
}


def sleep_ms(ms):
    try:
        time.sleep_ms(ms)
    except Exception:
        time.sleep(ms / 1000.0)


def set_pump(name, on):
    if name not in PUMPS:
        raise ValueError("unsupported pump: {}".format(name))
    pin = PUMPS[name]
    pin.value(0 if on else 1)
    return pin.value()


def pump_control(name, on_time=1000):
    if name not in PUMPS:
        raise ValueError("unsupported pump: {}".format(name))

    on_time = int(on_time)
    if on_time < 0:
        raise ValueError("on_time must be >= 0")

    set_pump(name, True)
    print("{} ON (gpio={}, raw=0)".format(name, PUMP_GPIO_MAP[name]))
    sleep_ms(on_time)
    set_pump(name, False)
    print("{} OFF (gpio={}, raw=1)".format(name, PUMP_GPIO_MAP[name]))
    return True


def print_status():
    for name in ("f1", "f2", "f3", "f4"):
        raw = PUMPS[name].value()
        logical = "ON" if raw == 0 else "OFF"
        print("{}: gpio={} {} (raw={})".format(name, PUMP_GPIO_MAP[name], logical, raw))


def print_help():
    print("=== Pump Control ===")
    print("active-low: ON=0, OFF=1")
    print("mapping: f1=GPIO10, f2=GPIO11, f3=GPIO12, f4=GPIO13")
    print("commands:")
    print("  f1 1000      -> run f1 for 1000ms")
    print("  on f1        -> turn f1 on")
    print("  off f1       -> turn f1 off")
    print("  status       -> show pump states")
    print("  all off      -> turn all pumps off")
    print("  q            -> quit")


def all_off():
    for name in PUMPS:
        set_pump(name, False)


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
            print("all pumps off")
            continue

        parts = cmd.split()

        if len(parts) == 2 and parts[0] in ("on", "off"):
            name = parts[1]
            try:
                raw = set_pump(name, parts[0] == "on")
                print("{} {} (raw={})".format(name, parts[0].upper(), raw))
            except ValueError as exc:
                print(exc)
            continue

        if len(parts) == 2:
            name = parts[0]
            try:
                on_time = int(parts[1])
                pump_control(name, on_time=on_time)
            except ValueError as exc:
                print(exc)
            continue

        print("invalid command")


if __name__ == "__main__":
    main()

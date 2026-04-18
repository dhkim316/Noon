from machine import Pin


GPIO_PINS = {
    10: Pin(10, Pin.OUT, value=1),
    11: Pin(11, Pin.OUT, value=1),
    12: Pin(12, Pin.OUT, value=1),
    13: Pin(13, Pin.OUT, value=1),
}


def set_pin(pin_no, state):
    pin = GPIO_PINS[pin_no]
    pin.value(0 if state else 1)
    print("GPIO{} -> {} (raw={})".format(pin_no, "ON" if state else "OFF", pin.value()))


def print_help():
    print("=== GPIO 10~13 Manual Control ===")
    print("Commands:")
    print("  on <pin>   : turn pin on")
    print("  off <pin>  : turn pin off")
    print("  all on     : turn all pins on")
    print("  all off    : turn all pins off")
    print("  status     : show current pin states")
    print("  q          : quit")


def print_status():
    for pin_no in sorted(GPIO_PINS):
        raw = GPIO_PINS[pin_no].value()
        logical = "ON" if raw == 0 else "OFF"
        print("GPIO{} = {} (raw={})".format(pin_no, logical, raw))


def all_set(state):
    for pin_no in sorted(GPIO_PINS):
        set_pin(pin_no, state)


def main():
    print_help()
    print_status()

    while True:
        cmd = input("cmd> ").strip().lower()
        if not cmd:
            continue
        if cmd == "q":
            all_set(False)
            print("quit")
            break
        if cmd == "status":
            print_status()
            continue
        if cmd == "all on":
            all_set(True)
            continue
        if cmd == "all off":
            all_set(False)
            continue

        parts = cmd.split()
        if len(parts) != 2 or parts[0] not in ("on", "off"):
            print("invalid command")
            continue

        try:
            pin_no = int(parts[1])
        except ValueError:
            print("pin must be a number")
            continue

        if pin_no not in GPIO_PINS:
            print("supported pins: 10, 11, 12, 13")
            continue

        set_pin(pin_no, parts[0] == "on")


if __name__ == "__main__":
    main()

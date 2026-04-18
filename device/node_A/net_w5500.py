from machine import Pin, SPI, unique_id
import network
import socket
import time


# -------------------------
# Fixed wiring (hard-coded)
# -------------------------
_SPI_ID = 0
_SPI_BAUD = 20_000_000
_PIN_SCK = 18
_PIN_MOSI = 19
_PIN_MISO = 20
_PIN_CS = 21
_PIN_RST = 22


def _w5500_reset(rst: Pin, low_ms: int = 50, boot_ms: int = 200):
    # W5500 reset is typically active-low
    rst.value(0)
    time.sleep_ms(low_ms)
    rst.value(1)
    time.sleep_ms(boot_ms)


def _normalize_ip(net: dict) -> str:
    """Allow ip='192.168.1.' convenience.

    If net['ip'] ends with '.', append:
      - net['ip_last'] if provided
      - else a deterministic value from unique_id (range 200..249)
    """
    ip = str(net.get("ip", ""))
    if ip.endswith("."):
        if "ip_last" in net:
            last = int(net["ip_last"]) & 0xFF
        else:
            uid = unique_id()
            b = uid[-1] if len(uid) else 0
            last = 200 + (b % 50)  # 200..249
        return ip + str(last)
    return ip


def _make_mac(net: dict) -> bytes:
    """Build MAC address.

    Rule:
      - First 3 bytes: keep as configured (NET['mac'] first 3 bytes, or NET['mac_prefix'])
      - Last 3 bytes : MCU unique_id() last 3 bytes

    Returns 6-byte MAC.
    """
    # Prefix source priority: mac_prefix(3 bytes) > mac(6 bytes or >=3) > default prefix
    prefix = net.get("mac_prefix", None)
    if isinstance(prefix, (bytes, bytearray)) and len(prefix) >= 3:
        prefix3 = bytes(prefix[:3])
    else:
        prefix3 = b"\x02\x00\x00"  # locally administered default

    uid = unique_id()
    tail3 = uid[-3:] if len(uid) >= 3 else uid.ljust(3, b"\x00")
    return prefix3 + tail3

class W5500Net:
    """Minimal W5500 network helper."""

    def __init__(self, net: dict):
        if not isinstance(net, dict):
            raise TypeError("net must be a dict (e.g., netConfig.NET)")
        self.net = net
        self.nic = None

    def bringup(self, dhcp: bool = False, verbose: bool = True):
        """Initialize W5500 NIC.

        - dhcp=False: use static ip from self.net
        - dhcp=True: use DHCP (ignores ip/netmask/gw)
        """
        spi = SPI(
            _SPI_ID,
            baudrate=_SPI_BAUD,
            polarity=0,
            phase=0,
            sck=Pin(_PIN_SCK),
            mosi=Pin(_PIN_MOSI),
            miso=Pin(_PIN_MISO),
        )

        cs = Pin(_PIN_CS, Pin.OUT, value=1)
        rst = Pin(_PIN_RST, Pin.OUT, value=1)

        _w5500_reset(rst)

        self.nic = network.WIZNET5K(spi, cs, rst)
        self.nic.active(True)

        # MAC: keep first 3 bytes from config, last 3 bytes from unique_id()
        mac = _make_mac(self.net)
        try:
            self.nic.config(mac=mac)
        except Exception:
            try:
                self.nic.config("mac", mac)
            except Exception:
                # If not supported by this firmware, ignore silently
                pass

        ip = _normalize_ip(self.net)
        netmask = self.net.get("netmask", "255.255.255.0")
        gw = self.net.get("gw", "192.168.1.1")
        dns = self.net.get("dns", gw)
        self.nic.ifconfig((ip, netmask, gw, dns))

        if verbose:
            print("ifconfig:", self.nic.ifconfig())
            self.print_mac()
            print("pc_ip:", self.net.get("pc_ip"))
            print("pc_port:", self.net.get("pc_port", self.net.get("server_port")))

        return self.nic

    def get_mac(self):
        """Return current MAC as 6-byte bytes, or None if unsupported."""
        if self.nic is None:
            return None
        # MicroPython NICs typically support nic.config('mac')
        try:
            mac = self.nic.config('mac')
            if isinstance(mac, (bytes, bytearray)) and len(mac) == 6:
                return bytes(mac)
        except Exception:
            pass
        return None

    def print_mac(self, prefix: str = "MAC"):
        """Print MAC in human-readable form."""
        mac = self.get_mac()
        if mac is None:
            print(prefix + ": <unavailable>")
            return None
        mac_str = ":".join("%02X" % b for b in mac)
        print(prefix + ":", mac_str)
        return mac_str

    def ifconfig(self):
        if self.nic is None:
            return None
        return self.nic.ifconfig()

    def make_server(self, port: int, backlog: int = 1, timeout_s: float = 1.0):
        """Create a simple TCP listening socket."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass
        s.bind(("0.0.0.0", int(port)))
        s.listen(int(backlog))
        try:
            s.settimeout(timeout_s)
        except Exception:
            pass
        return s

    def make_client(self, host: str, port: int, timeout_s: float = 3.0):
        """Create a simple TCP client socket and connect."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(timeout_s)
        except Exception:
            pass
        s.connect((host, int(port)))
        return s

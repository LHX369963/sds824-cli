from __future__ import annotations

import array
import fcntl
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import TransportError

USBTMC_IOCTL_CLEAR = 0x5B02
USBTMC_IOCTL_SET_TIMEOUT = 0x40045B0A
USBTMC_IOCTL_EOM_ENABLE = 0x40015B0B
SIGLENT_VENDOR_ID = "f4ec"
SDS824_PRODUCT_ID = "1017"


@dataclass(frozen=True)
class DeviceInfo:
    path: Path
    manufacturer: str
    product: str
    serial: str
    vendor_id: str
    product_id: str


def _read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def discover_devices() -> list[DeviceInfo]:
    devices: list[DeviceInfo] = []
    for node in sorted(Path("/dev").glob("usbtmc*")):
        class_link = Path("/sys/class/usbmisc") / node.name / "device"
        try:
            usb_device = class_link.resolve().parent
        except OSError:
            continue
        vendor_id = _read_text(usb_device / "idVendor").lower()
        manufacturer = _read_text(usb_device / "manufacturer")
        if vendor_id != SIGLENT_VENDOR_ID and "siglent" not in manufacturer.lower():
            continue
        devices.append(DeviceInfo(
            path=node,
            manufacturer=manufacturer,
            product=_read_text(usb_device / "product"),
            serial=_read_text(usb_device / "serial"),
            vendor_id=vendor_id,
            product_id=_read_text(usb_device / "idProduct").lower(),
        ))
    return devices


def choose_device(path: str | None = None, serial: str | None = None) -> DeviceInfo:
    devices = discover_devices()
    if path is not None:
        requested = Path(path).resolve() if Path(path).is_symlink() else Path(path)
        matches = [item for item in devices if item.path == requested or item.path.resolve() == requested]
        if not matches:
            raise TransportError(f"no SIGLENT USBTMC device found at {path}")
        return matches[0]
    if serial is not None:
        matches = [item for item in devices if item.serial == serial]
        if not matches:
            raise TransportError(f"no SIGLENT USBTMC device found with serial {serial!r}")
        if len(matches) > 1:
            raise TransportError(f"multiple SIGLENT devices report serial {serial!r}")
        return matches[0]
    scopes = [item for item in devices if item.product_id == SDS824_PRODUCT_ID or item.serial.upper().startswith("SDS08")]
    if not scopes:
        raise TransportError("no SDS824 USBTMC device found; connect it and run 'sds824 list'")
    if len(scopes) > 1:
        paths = ", ".join(str(item.path) for item in scopes)
        raise TransportError(f"multiple SDS824 scopes found ({paths}); use --device or --serial")
    return scopes[0]


class LinuxUsbtmc:
    """Dependency-free, exclusively locked Linux USBTMC character-device session."""

    def __init__(self, device: DeviceInfo, *, timeout_ms: int = 10000,
                 clear_on_open: bool = True, command_delay_ms: float = 10.0) -> None:
        if timeout_ms <= 0:
            raise TransportError("timeout must be positive")
        if command_delay_ms < 0:
            raise TransportError("command delay cannot be negative")
        self.device = device
        self.timeout_ms = timeout_ms
        self.clear_on_open = clear_on_open
        self.command_delay_ms = command_delay_ms
        self._fd: int | None = None

    def __enter__(self) -> "LinuxUsbtmc":
        try:
            self._fd = os.open(self.device.path, os.O_RDWR)
            fcntl.flock(self._fd, fcntl.LOCK_EX)
            fcntl.ioctl(self._fd, USBTMC_IOCTL_SET_TIMEOUT, array.array("I", [self.timeout_ms]), True)
            fcntl.ioctl(self._fd, USBTMC_IOCTL_EOM_ENABLE, array.array("B", [1]), True)
            if self.clear_on_open:
                fcntl.ioctl(self._fd, USBTMC_IOCTL_CLEAR)
        except OSError as exc:
            self.close()
            if exc.errno in {1, 13}:
                raise TransportError(
                    f"permission denied opening {self.device.path}; install the supplied udev rule"
                ) from exc
            raise TransportError(f"cannot initialize {self.device.path}: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    @property
    def fd(self) -> int:
        if self._fd is None:
            raise TransportError("USBTMC session is not open")
        return self._fd

    @staticmethod
    def _encode(command: str | bytes) -> bytes:
        if isinstance(command, str):
            try:
                payload = command.encode("ascii")
            except UnicodeEncodeError as exc:
                raise TransportError("SCPI commands must contain ASCII characters only") from exc
        else:
            payload = bytes(command)
        if b"\n" in payload.rstrip(b"\r\n"):
            raise TransportError("a command cannot contain embedded newlines")
        return payload.rstrip(b"\r\n") + b"\n"

    def write(self, command: str | bytes, *, settle: bool = True) -> int:
        payload = self._encode(command)
        try:
            written = os.write(self.fd, payload)
        except OSError as exc:
            raise TransportError(f"USBTMC write failed: {exc}") from exc
        if settle and self.command_delay_ms:
            time.sleep(self.command_delay_ms / 1000)
        return written

    def write_raw(self, payload: bytes) -> int:
        try:
            return os.write(self.fd, payload)
        except OSError as exc:
            raise TransportError(f"USBTMC raw write failed: {exc}") from exc

    def read(self, *, max_bytes: int = 128 * 1024 * 1024) -> bytes:
        if max_bytes <= 0:
            raise TransportError("read size must be positive")
        try:
            return os.read(self.fd, max_bytes)
        except OSError as exc:
            raise TransportError(f"USBTMC read failed: {exc}") from exc

    def query(self, command: str | bytes, *, max_bytes: int = 128 * 1024 * 1024) -> bytes:
        self.write(command, settle=False)
        return self.read(max_bytes=max_bytes)

    def query_text(self, command: str, *, max_bytes: int = 1024 * 1024) -> str:
        data = self.query(command, max_bytes=max_bytes)
        try:
            return data.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise TransportError("instrument returned binary data to a text query") from exc

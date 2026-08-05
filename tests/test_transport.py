import pytest

import sds824_cli.transport as transport
from sds824_cli.errors import TransportError
from sds824_cli.transport import DeviceInfo, LinuxUsbtmc


def test_encode_adds_one_terminator():
    assert LinuxUsbtmc._encode(":RUN") == b":RUN\n"
    assert LinuxUsbtmc._encode(b"*IDN?\r\n") == b"*IDN?\n"


def test_encode_rejects_embedded_newline_and_unicode():
    with pytest.raises(TransportError, match="embedded newlines"):
        LinuxUsbtmc._encode(":RUN\n:STOP")
    with pytest.raises(TransportError, match="ASCII"):
        LinuxUsbtmc._encode("中文")


def test_invalid_timing_is_rejected():
    device = type("Device", (), {})()
    with pytest.raises(TransportError, match="positive"):
        LinuxUsbtmc(device, timeout_ms=0)
    with pytest.raises(TransportError, match="negative"):
        LinuxUsbtmc(device, command_delay_ms=-1)


def test_query_does_not_add_fixed_settle_delay(monkeypatch):
    device = type("Device", (), {})()
    transport = LinuxUsbtmc(device, command_delay_ms=10)
    transport._fd = 7
    sleeps = []
    monkeypatch.setattr("sds824_cli.transport.os.write", lambda fd, payload: len(payload))
    monkeypatch.setattr("sds824_cli.transport.os.read", lambda fd, size: b"1\n")
    monkeypatch.setattr("sds824_cli.transport.time.sleep", sleeps.append)
    assert transport.query_text("*OPC?") == "1"
    assert sleeps == []
    transport.write(":TRIG:RUN")
    assert sleeps == [0.01]


def test_query_rejects_empty_response(monkeypatch):
    device = type("Device", (), {})()
    transport = LinuxUsbtmc(device)
    transport._fd = 7
    monkeypatch.setattr("sds824_cli.transport.os.write", lambda fd, payload: len(payload))
    monkeypatch.setattr("sds824_cli.transport.os.read", lambda fd, size: b"")
    with pytest.raises(TransportError, match="empty response"):
        transport.query_text("*IDN?")


def test_query_clears_and_retries_after_timeout(monkeypatch):
    device = type("Device", (), {})()
    transport = LinuxUsbtmc(device)
    transport._fd = 7
    reads = [OSError(110, "timed out"), b"OK\n"]
    clears = []
    sleeps = []

    monkeypatch.setattr("sds824_cli.transport.os.write", lambda fd, payload: len(payload))

    def fake_read(fd, size):
        value = reads.pop(0)
        if isinstance(value, OSError):
            raise value
        return value

    monkeypatch.setattr("sds824_cli.transport.os.read", fake_read)
    monkeypatch.setattr("sds824_cli.transport.fcntl.ioctl", lambda fd, request, *args: clears.append(request))
    monkeypatch.setattr("sds824_cli.transport.time.sleep", sleeps.append)
    assert transport.query_text("*IDN?", retries=1, retry_delay_ms=250) == "OK"
    assert clears
    assert sleeps == [0.25]


def test_explicit_device_does_not_scan(monkeypatch):
    expected = DeviceInfo(
        transport.Path("/dev/usbtmc7"), "SIGLENT", "SDS824X HD", "S", "f4ec", "1017"
    )
    monkeypatch.setattr(transport, "_device_info", lambda node: expected)
    monkeypatch.setattr(transport, "discover_devices", lambda: pytest.fail("scanned devices"))
    assert transport.choose_device("/dev/usbtmc7") == expected

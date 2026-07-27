import struct

import pytest

from sds824_cli.errors import ProtocolError
from sds824_cli.waveform import Waveform, parse_ieee_block, parse_preamble, write_waveform


def block(payload: bytes) -> bytes:
    length = str(len(payload)).encode()
    return b"#" + str(len(length)).encode() + length + payload + b"\n"


def preamble_payload() -> bytes:
    p = bytearray(346)
    p[:8] = b"WAVEDESC"
    struct.pack_into("<h", p, 32, 1)
    struct.pack_into("<h", p, 34, 0)
    struct.pack_into("<i", p, 36, 346)
    struct.pack_into("<i", p, 60, 4)
    struct.pack_into("<i", p, 116, 2)
    struct.pack_into("<i", p, 132, 10)
    struct.pack_into("<i", p, 136, 2)
    struct.pack_into("<f", p, 156, 0.5)
    struct.pack_into("<f", p, 160, 0.25)
    struct.pack_into("<f", p, 164, 30.0)
    struct.pack_into("<h", p, 172, 12)
    struct.pack_into("<f", p, 176, 1e-6)
    struct.pack_into("<d", p, 180, -2e-3)
    struct.pack_into("<f", p, 328, 10.0)
    return bytes(p)


def test_parse_definite_block_and_reject_truncation():
    assert parse_ieee_block(b"#14abcd\n") == b"abcd"
    with pytest.raises(ProtocolError, match="truncated block"):
        parse_ieee_block(b"#14abc")


def test_parse_siglent_preamble_and_convert_word_samples(tmp_path):
    pre = parse_preamble(block(preamble_payload()))
    assert pre.points == 2
    assert pre.bytes_per_point == 2
    wave = Waveform("C1", pre, struct.pack("<hh", 30, -30))
    assert wave.codes() == [30, -30]
    assert wave.voltage(30) == pytest.approx(2.5)
    assert wave.voltage(-30) == pytest.approx(-7.5)
    assert wave.time_at(0) == pytest.approx(-0.00199)
    path = tmp_path / "wave.csv"
    write_waveform(wave, path, "csv")
    assert path.read_text().splitlines()[0] == "index,time_seconds,code,volts"


def test_byte_transfer_uses_high_adc_byte_weight():
    payload = bytearray(preamble_payload())
    struct.pack_into("<h", payload, 32, 0)
    struct.pack_into("<f", payload, 164, 7680.0)
    struct.pack_into("<h", payload, 172, 16)
    pre = parse_preamble(block(bytes(payload)))
    wave = Waveform("C1", pre, struct.pack("bb", 60, -60))
    assert wave.voltage(60) == pytest.approx(7.5)
    assert wave.voltage(-60) == pytest.approx(-12.5)


def test_preamble_signature_is_checked():
    with pytest.raises(ProtocolError, match="WAVEDESC"):
        parse_preamble(block(bytes(346)))

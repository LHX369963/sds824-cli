from __future__ import annotations

import csv
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import ProtocolError


def parse_ieee_block(data: bytes) -> bytes:
    if not data.startswith(b"#"):
        return data.rstrip(b"\r\n")
    if len(data) < 2 or not chr(data[1]).isdigit():
        raise ProtocolError("invalid IEEE 488.2 block header")
    digits = data[1] - ord("0")
    if digits == 0:
        return data[2:].rstrip(b"\r\n")
    if len(data) < 2 + digits:
        raise ProtocolError("truncated IEEE 488.2 block length")
    try:
        length = int(data[2:2 + digits])
    except ValueError as exc:
        raise ProtocolError("invalid IEEE 488.2 block length") from exc
    start = 2 + digits
    end = start + length
    if len(data) < end:
        raise ProtocolError(f"truncated block: expected {length} payload bytes, got {len(data) - start}")
    return data[start:end]


@dataclass(frozen=True)
class WaveformPreamble:
    comm_type: int
    comm_order: int
    descriptor_bytes: int
    data_bytes: int
    points: int
    start: int
    interval: int
    read_frames: int
    total_frames: int
    vertical_scale: float
    vertical_offset: float
    codes_per_div: float
    adc_bits: int
    frame: int
    sample_interval: float
    horizontal_delay: float
    timebase_index: int
    coupling: int
    probe_factor: float
    bandwidth_limit: int
    source_index: int

    @property
    def byte_order(self) -> str:
        return "little" if self.comm_order == 0 else "big"

    @property
    def bytes_per_point(self) -> int:
        return 1 if self.comm_type == 0 else 2


def parse_preamble(data: bytes) -> WaveformPreamble:
    payload = parse_ieee_block(data)
    if len(payload) < 346:
        raise ProtocolError(f"waveform preamble must be 346 bytes, got {len(payload)}")
    if not payload.startswith(b"WAVEDESC"):
        raise ProtocolError("waveform preamble lacks WAVEDESC signature")
    # COMM_ORDER is itself encoded in the native descriptor order.  Values 0/1
    # have unambiguous zero-byte patterns, so inspect both interpretations.
    little = struct.unpack_from("<h", payload, 34)[0]
    big = struct.unpack_from(">h", payload, 34)[0]
    endian = "<" if little in {0, 1} else ">" if big in {0, 1} else None
    if endian is None:
        raise ProtocolError("invalid preamble byte order")
    i16 = lambda offset: struct.unpack_from(endian + "h", payload, offset)[0]
    i32 = lambda offset: struct.unpack_from(endian + "i", payload, offset)[0]
    f32 = lambda offset: struct.unpack_from(endian + "f", payload, offset)[0]
    f64 = lambda offset: struct.unpack_from(endian + "d", payload, offset)[0]
    return WaveformPreamble(
        comm_type=i16(32), comm_order=i16(34), descriptor_bytes=i32(36),
        data_bytes=i32(60), points=i32(116), start=i32(132), interval=i32(136),
        read_frames=i32(144), total_frames=i32(148), vertical_scale=f32(156),
        vertical_offset=f32(160), codes_per_div=f32(164), adc_bits=i16(172),
        frame=i16(174), sample_interval=f32(176), horizontal_delay=f64(180),
        timebase_index=i16(324), coupling=i16(326), probe_factor=f32(328),
        bandwidth_limit=i16(334), source_index=i16(344),
    )


@dataclass(frozen=True)
class Waveform:
    source: str
    preamble: WaveformPreamble
    raw: bytes

    @property
    def point_count(self) -> int:
        return len(self.raw) // self.preamble.bytes_per_point

    def codes(self) -> list[int]:
        if self.preamble.bytes_per_point == 1:
            return list(struct.unpack(f"{len(self.raw)}b", self.raw))
        if len(self.raw) % 2:
            raise ProtocolError("16-bit waveform has an odd byte count")
        endian = "<" if self.preamble.comm_order == 0 else ">"
        return list(struct.unpack(endian + f"{len(self.raw) // 2}h", self.raw))

    def voltage(self, code: int) -> float:
        if self.preamble.codes_per_div == 0:
            raise ProtocolError("preamble reports zero codes per division")
        factor = self.preamble.probe_factor
        return code * (self.preamble.vertical_scale * factor / self.preamble.codes_per_div) - self.preamble.vertical_offset * factor

    def time_at(self, index: int) -> float:
        return self.preamble.horizontal_delay + (
            self.preamble.start + index * self.preamble.interval
        ) * self.preamble.sample_interval


def write_waveform(waveform: Waveform, path: Path, output_format: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "bin":
        path.write_bytes(waveform.raw)
        return
    codes = waveform.codes()
    if output_format == "csv":
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["index", "time_seconds", "code", "volts"])
            for index, code in enumerate(codes):
                writer.writerow([index, waveform.time_at(index), code, waveform.voltage(code)])
        return
    if output_format == "json":
        path.write_text(json.dumps({
            "source": waveform.source,
            "points": waveform.point_count,
            "preamble": asdict(waveform.preamble),
            "samples": [
                {"index": i, "time_seconds": waveform.time_at(i), "code": code, "volts": waveform.voltage(code)}
                for i, code in enumerate(codes)
            ],
        }, indent=2) + "\n")
        return
    raise ProtocolError(f"unsupported waveform format {output_format!r}")

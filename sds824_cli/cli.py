from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
import sys
import time
from collections.abc import Sequence
from contextlib import contextmanager, suppress
from dataclasses import asdict
from pathlib import Path

from .catalog import COMMANDS, get_command, render_command
from .errors import ProtocolError, Sds824Error, TransportError
from .parameters import can_verify_set, set_values_equivalent, validate_set_values
from .transport import LinuxUsbtmc, choose_device, discover_devices, reset_usb_device
from .waveform import Waveform, parse_ieee_block, parse_preamble, write_waveform

INDEX_NAMES = ("n", "x", "m", "r", "d", "channel")
DESTRUCTIVE_ACTIONS = {
    "ieee.rst", "root.autoset", "digital.bus.n.default", "recall.reference",
    "recall.setup", "save.default", "mtest.reset",
}
_NEGATIVE_VALUE_PREFIX = "__SDS824_NEGATIVE_VALUE__"


def _protect_negative_values(argv: Sequence[str]) -> list[str]:
    pattern = re.compile(r"^-(?:\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|GREaterthan|LESSthan)$", re.IGNORECASE)
    return [_NEGATIVE_VALUE_PREFIX + value if pattern.fullmatch(value) else value for value in argv]


def _restore_negative_values(args: argparse.Namespace) -> None:
    for name, value in vars(args).items():
        if isinstance(value, str) and value.startswith(_NEGATIVE_VALUE_PREFIX):
            setattr(args, name, value.removeprefix(_NEGATIVE_VALUE_PREFIX))
        elif isinstance(value, list):
            setattr(args, name, [
                item.removeprefix(_NEGATIVE_VALUE_PREFIX)
                if isinstance(item, str) and item.startswith(_NEGATIVE_VALUE_PREFIX) else item
                for item in value
            ])


MEASURE_TYPES = (
    "PKPK", "MAX", "MIN", "AMPL", "TOP", "BASE", "LEVELX", "CMEAN",
    "MEAN", "STDEV", "VSTD", "RMS", "CRMS", "MEDIAN", "CMEDIAN",
    "OVSN", "FPRE", "OVSP", "RPRE", "ULOWER", "PER", "FREQ", "TMAX",
    "TMIN", "PWID", "NWID", "DUTY", "NDUTY", "WID", "NBWID", "DELAY",
    "TIMEL", "RISE", "FALL", "RISE20T80", "FALL80T20", "CCJ", "PAREA",
    "NAREA", "AREA", "ABSAREA", "CYCLES", "REDGES", "FEDGES", "EDGES",
    "PPULSES", "NPULSES", "PACAREA", "NACAREA", "ACAREA", "ABSACAREA",
)
SDS824_UNSUPPORTED_MEASURE_TYPES = {"RISE20T80", "FALL80T20"}


def _add_connection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", help="USBTMC node (automatic SDS824 selection by default)")
    parser.add_argument("--serial", help="select the USB descriptor serial number")
    parser.add_argument(
        "--timeout", type=int,
        help="USBTMC timeout in milliseconds (default: 30000 for screenshots, 10000 otherwise)",
    )
    parser.add_argument("--command-delay", type=float, default=10.0, help="delay after non-query writes in milliseconds")
    parser.add_argument(
        "--clear-on-open", action="store_true",
        help="explicitly issue USBTMC CLEAR when opening",
    )
    parser.add_argument("--no-clear", action="store_false", dest="clear_on_open", help=argparse.SUPPRESS)


def _add_indices(parser: argparse.ArgumentParser) -> None:
    for name in INDEX_NAMES:
        parser.add_argument(f"--{name}", help=f"replace manual command path placeholder <{name}>")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sds824", description="SIGLENT SDS824X HD USBTMC CLI")
    _add_connection(parser)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list attached SIGLENT USBTMC devices")
    sub.add_parser("info", help="query identity and USB selection")
    sub.add_parser("config", help="query a practical acquisition/channel/trigger snapshot")
    recover = sub.add_parser("recover", help="clear USBTMC and verify SCPI health")
    recover.add_argument("--attempts", type=int, default=3)
    recover.add_argument("--delay", type=float, default=0.5, help="seconds between health probes")
    recover.add_argument("--usb-reset", action="store_true", help="reset the USB device if CLEAR retries fail")

    commands = sub.add_parser("commands", help="inspect the complete programming-guide catalog")
    csub = commands.add_subparsers(dest="commands_command", required=True)
    clist = csub.add_parser("list")
    clist.add_argument("--section", help="section number (for example 5.22) or text filter")
    clist.add_argument("--queryable", action="store_true")
    clist.add_argument("--writable", action="store_true")
    cshow = csub.add_parser("show")
    cshow.add_argument("name")
    cshow.add_argument("--verbose", action="store_true", help="show complete manual metadata")
    cshow.add_argument("--json", action="store_true", help="emit JSON")
    cshow.add_argument("--pretty", action="store_true", help="indent JSON output")
    csub.add_parser("audit", help="summarize catalog/manual extraction coverage")

    get = sub.add_parser("get", help="query a catalog command")
    get.add_argument("name")
    get.add_argument("values", nargs="*", help="query arguments declared after '?' in the guide")
    _add_indices(get)
    get.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    get.add_argument("--output", type=Path, help="write raw response bytes to a file")
    get.add_argument("--binary", action="store_true", help="write raw response to stdout")
    get.add_argument("--allow-unsupported", action="store_true", help="explicitly access optional/other-model catalog paths")

    setp = sub.add_parser("set", help="write a query-set catalog command")
    setp.add_argument("name")
    setp.add_argument("values", nargs="+", help="command values, joined with spaces")
    _add_indices(setp)
    setp.add_argument("--allow-unsupported", action="store_true", help="explicitly access optional/other-model catalog paths")
    setp.add_argument("--no-verify", action="store_true", help="skip readback verification for a write")

    action = sub.add_parser("action", help="execute a catalog action")
    action.add_argument("name")
    action.add_argument("values", nargs="*", help="action arguments")
    _add_indices(action)
    action.add_argument("--yes", action="store_true", help="confirm broad/destructive state changes")
    action.add_argument("--allow-unsupported", action="store_true", help="explicitly access optional/other-model catalog paths")

    raw = sub.add_parser("raw", help="send one arbitrary SCPI command")
    raw.add_argument("scpi")
    raw.add_argument("--read", action="store_true")
    raw.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    raw.add_argument("--output", type=Path)
    raw.add_argument("--binary", action="store_true")

    batch = sub.add_parser("batch", help="execute SCPI lines from a file or '-' for stdin")
    batch.add_argument("file", type=Path)

    measure = sub.add_parser("measure", help="read selected or all simple measurements")
    measure.add_argument("metrics", nargs="+", metavar="METRIC", help="measurement names, e.g. freq pkpk mean")
    measure.add_argument("--source", default="C1", help="C1, C2, F1, M1, etc.")
    measure.add_argument("--vertical-scale", help="set channel volts/div first, e.g. 200mV")
    measure.add_argument("--time-scale", help="set time/div first, e.g. 200us")
    measure.add_argument("--coupling", choices=("DC", "AC", "GND"), help="set channel coupling first")
    measure.add_argument("--expect-frequency", help="expected frequency used to choose time/div")
    measure.add_argument("--expect-pkpk", help="expected peak-to-peak voltage used to choose volts/div")
    measure.add_argument("--expect-offset", help="expected DC center used to choose channel offset")
    measure.add_argument("--json", action="store_true")
    measure.add_argument("--include-unavailable", action="store_true", help="include unavailable values such as ****")
    measure.add_argument("--pretty", action="store_true", help="indent JSON output")

    screen = sub.add_parser("screenshot", help="download the current display")
    screen.add_argument("output", type=Path)
    screen.add_argument("--format", choices=("png", "bmp"), default="png")
    screen.add_argument("--inverted", action="store_true")
    screen.add_argument("--retries", type=int, default=1, help="retry after USBTMC CLEAR on a timeout or empty response")
    screen.add_argument("--retry-delay", type=float, default=0.5, help="seconds before retrying the screenshot query")

    wave = sub.add_parser("waveform", help="download waveform data with its 346-byte preamble")
    wave.add_argument("output", type=Path)
    wave.add_argument("--source", default="C1")
    wave.add_argument("--format", choices=("bin", "csv", "json"), default="csv")
    wave.add_argument("--width", choices=("BYTE", "WORD"), default="WORD")
    wave.add_argument("--start", type=int, default=0)
    wave.add_argument(
        "--points",
        type=int,
        help="requested transfer points; omit to keep the instrument-selected count",
    )
    wave.add_argument("--interval", type=int, default=1)
    wave.add_argument("--stop", action="store_true", help="stop acquisition during transfer and restore RUN state")
    return parser


@contextmanager
def _session(args):
    device = choose_device(args.device, args.serial)
    timeout_ms = args.timeout
    if timeout_ms is None:
        timeout_ms = 30000 if args.command == "screenshot" else 10000
    with LinuxUsbtmc(device, timeout_ms=timeout_ms, clear_on_open=args.clear_on_open,
                     command_delay_ms=args.command_delay) as scope:
        yield scope


def _indices(args) -> dict[str, str | None]:
    return {name: getattr(args, name, None) for name in INDEX_NAMES}


def _format_scpi_arguments(spec, values: Sequence[str], *, query: bool = False) -> str:
    if not values:
        return ""
    if spec.name == "wgen.output" and not query:
        if len(values) != 3:
            raise ProtocolError("wgen.output requires state, load, and polarity")
        return f"{values[0]},LOAD,{values[1]},PLRT{values[2]}"
    formats = [
        item
        for item in spec.formats
        if ("?" in item.split(" ", 1)[0]) == query
    ]
    syntax = formats[0].split(" ", 1)[1] if formats and " " in formats[0] else ""
    separator = "," if len(values) > 1 and "," in syntax else " "
    return separator.join(values)


def _query_snapshot(scope: LinuxUsbtmc) -> dict:
    def q(command: str) -> str:
        return scope.query_text(command)
    return {
        "identity": q("*IDN?"),
        "acquisition": {
            "mode": q(":ACQuire:MODE?"), "type": q(":ACQuire:TYPE?"),
            "memory_depth": q(":ACQuire:MDEPth?"), "sample_rate": q(":ACQuire:SRATe?"),
            "points": q(":ACQuire:POINts?"),
        },
        "timebase": {"scale": q(":TIMebase:SCALe?"), "delay": q(":TIMebase:DELay?")},
        "channels": {
            f"C{n}": {key: q(f":CHANnel{n}:{command}?") for key, command in (
                ("switch", "SWITch"), ("visible", "VISible"), ("coupling", "COUPling"),
                ("impedance", "IMPedance"), ("probe", "PROBe"), ("scale", "SCALe"),
                ("offset", "OFFSet"), ("invert", "INVert"), ("bandwidth_limit", "BWLimit"),
            )} for n in (1, 2, 3, 4)
        },
        "trigger": {"status": q(":TRIGger:STATus?"), "mode": q(":TRIGger:MODE?"), "type": q(":TRIGger:TYPE?")},
    }


def _run_batch(scope: LinuxUsbtmc, lines) -> int:
    for line_number, raw_line in enumerate(lines, 1):
        command = raw_line.strip()
        if not command or command.startswith("#"):
            continue
        try:
            if "?" in command.split(" ", 1)[0]:
                print(scope.query_text(command))
            else:
                scope.write(command)
        except Sds824Error as exc:
            raise ProtocolError(f"batch line {line_number}: {exc}") from exc
    return 0


def _measure(
    scope: LinuxUsbtmc,
    metrics: list[str],
    source: str,
    *,
    autorange: bool = True,
    voltage_autorange: bool | None = None,
    time_autorange: bool | None = None,
) -> dict[str, str | float]:
    source = source.upper()
    if not re.fullmatch(r"(?:C[1-4]|F\d+|M\d+|REF[ABCD])", source):
        raise ProtocolError(f"unsupported simple measurement source {source!r}")
    if "all" in metrics and len(metrics) != 1:
        raise ProtocolError("all cannot be combined with individual measurements")
    unknown = [name for name in metrics if name != "all" and name.upper() not in MEASURE_TYPES]
    if unknown:
        raise ProtocolError(f"unknown measurement {unknown[0]!r}")
    requested = tuple(metric.upper() for metric in metrics)
    unsupported = next((name for name in requested if name in SDS824_UNSUPPORTED_MEASURE_TYPES), None)
    if unsupported is not None:
        raise ProtocolError(
            f"{unsupported} is documented for the series but times out on the tested SDS824 firmware"
        )
    old_display = scope.query_text(":MEASure?")
    old_source = scope.query_text(":MEASure:SIMPle:SOURce?")
    names = (
        tuple(name for name in MEASURE_TYPES if name not in SDS824_UNSUPPORTED_MEASURE_TYPES)
        if metrics == ["all"] else requested
    )
    range_names = tuple(dict.fromkeys((*names, "PKPK", "MAX", "MIN", "MEAN")))
    physical_measurement = bool(autorange and re.fullmatch(r"C[1-4]", source))
    voltage_autorange = physical_measurement if voltage_autorange is None else bool(
        physical_measurement and voltage_autorange
    )
    time_autorange = physical_measurement if time_autorange is None else bool(
        physical_measurement and time_autorange
    )
    query_names = range_names if physical_measurement else names
    sentinel: str | None = None
    last_groups: list[dict[str, str]] = []

    def sample_groups(*, count: int = 3, random_intervals: bool = False) -> dict[str, str | float]:
        nonlocal last_groups
        groups: list[dict[str, str]] = []
        for group in range(count):
            groups.append({
                name: scope.query_text(f":MEASure:SIMPle:VALue? {name}")
                for name in query_names
            })
            if group + 1 < count:
                time.sleep(random.uniform(0.12, 0.38) if random_intervals else 0.05)
        last_groups = groups
        result: dict[str, str | float] = {}
        for name in query_names:
            numeric: list[float] = []
            for group in groups:
                with suppress(ValueError):
                    numeric.append(float(group[name]))
            result[name] = statistics.median(numeric) if numeric else groups[-1][name]
        return result

    def trigger_and_sample(result: dict[str, str | float]) -> dict[str, str | float]:
        try:
            level = (float(result["MAX"]) + float(result["MIN"])) / 2.0
        except (KeyError, TypeError, ValueError):
            level = 0.0
        channel = source[1]
        for command in (
            ":TRIGger:TYPE EDGE",
            f":TRIGger:EDGE:SOURce C{channel}",
            ":TRIGger:EDGE:SLOPe RISing",
            f":TRIGger:EDGE:LEVel {level:.12g}",
            ":TRIGger:MODE AUTO",
            ":TRIGger:RUN",
        ):
            scope.write(command)
        time.sleep(random.uniform(0.12, 0.38))
        try:
            trigger_status = scope.query_text(":TRIGger:STATus?").strip()
        except Sds824Error:
            trigger_status = "unknown"
        if trigger_status.lower() not in {"trig'd", "triggered", "stop"}:
            print(f"warning: trigger {trigger_status}", file=sys.stderr)
        final = sample_groups(count=5, random_intervals=True)
        unstable: list[str] = []
        pkpk_reference = abs(float(final.get("PKPK", 0.0))) if isinstance(final.get("PKPK"), float) else 0.0
        for name in names:
            numeric: list[float] = []
            for group in last_groups:
                with suppress(ValueError):
                    numeric.append(float(group[name]))
            if len(numeric) != len(last_groups):
                unstable.append(name.lower() + "=intermittent")
                continue
            span = max(numeric) - min(numeric)
            median = abs(statistics.median(numeric))
            if name in {"DUTY", "NDUTY"}:
                changed = span > 2.0
            elif name in {"MEAN", "CMEAN", "MEDIAN", "CMEDIAN"}:
                changed = span > max(pkpk_reference * 0.1, 1e-9)
            else:
                changed = span > max(median * 0.1, 1e-12)
            if changed:
                unstable.append(f"{name.lower()}={min(numeric):.6g}..{max(numeric):.6g}")
        if unstable:
            print("warning: unstable " + " ".join(unstable), file=sys.stderr)
        return final

    def next_scale(value: float) -> float:
        value = min(10.0, max(5e-4, value))
        decade = 10.0 ** math.floor(math.log10(value))
        for step in (1.0, 2.0, 5.0, 10.0):
            candidate = step * decade
            if candidate >= value * (1.0 - 1e-12):
                return min(10.0, max(5e-4, candidate))
        raise AssertionError("unreachable")

    def next_125(value: float) -> float:
        decade = 10.0 ** math.floor(math.log10(value))
        normalized = value / decade
        for step in (2.0, 5.0, 10.0):
            if step > normalized * (1.0 + 1e-9):
                return step * decade
        return 2.0 * decade * 10.0

    try:
        if physical_measurement:
            scope.write(f":CHANnel{source[1]}:SWITch ON")
        if old_display.upper() != "ON":
            scope.write(":MEASure ON")
        scope.write(f":MEASure:SIMPle:SOURce {source}")
        probe = scope.query_text(f":MEASure:SIMPle:VALue? {query_names[0]}")
        if not _measurement_value_available(probe):
            sentinel = query_names[0]
            scope.write(f":MEASure:SIMPle:ITEM {sentinel},ON")
        time.sleep(0.2)
        result = sample_groups()
        if physical_measurement:
            channel = source[1]
            if voltage_autorange:
                for attempt in range(2):
                    try:
                        scale = float(scope.query_text(f":CHANnel{channel}:SCALe?"))
                        offset = float(scope.query_text(f":CHANnel{channel}:OFFSet?"))
                        pkpk = float(result["PKPK"])
                        maximum = float(result["MAX"])
                        minimum = float(result["MIN"])
                    except (TypeError, ValueError):
                        break
                    center = -offset
                    near_edge = (
                        maximum >= center + 3.5 * scale
                        or minimum <= center - 3.5 * scale
                    )
                    occupancy = pkpk / scale if scale > 0 else math.inf
                    if not near_edge and 2.0 <= occupancy <= 7.0:
                        break
                    target = next_scale(max(pkpk / 5.0, scale * 1.5) if near_edge else pkpk / 5.0)
                    if math.isclose(target, scale, rel_tol=1e-9):
                        break
                    signal_center = (maximum + minimum) / 2.0
                    scope.write(f":CHANnel{channel}:SCALe {target:.12g}")
                    scope.write(f":CHANnel{channel}:OFFSet {-signal_center:.12g}")
                    time.sleep(0.5)
                    result = sample_groups()
                    if attempt == 0:
                        try:
                            new_pkpk = float(result["PKPK"])
                            new_max = float(result["MAX"])
                            new_min = float(result["MIN"])
                        except (TypeError, ValueError):
                            break
                        new_center = signal_center
                        still_clipped = (
                            new_max >= new_center + 3.5 * target
                            or new_min <= new_center - 3.5 * target
                            or new_pkpk / target > 7.0
                        )
                        if still_clipped:
                            second = next_scale(max(new_pkpk / 5.0, target * 1.5))
                            if second > target:
                                new_signal_center = (new_max + new_min) / 2.0
                                scope.write(f":CHANnel{channel}:SCALe {second:.12g}")
                                scope.write(f":CHANnel{channel}:OFFSet {-new_signal_center:.12g}")
                                time.sleep(0.5)
                                result = sample_groups()
                        break
            timing = [name for name in names if name in {"FREQ", "PER"}]
            if time_autorange and timing and not any(isinstance(result[name], float) for name in timing):
                try:
                    time_scale = float(scope.query_text(":TIMebase:SCALe?"))
                except ValueError:
                    time_scale = 0.0
                for _ in range(3):
                    if time_scale <= 0:
                        break
                    time_scale = next_125(time_scale)
                    scope.write(f":TIMebase:SCALe {time_scale:.12g}")
                    time.sleep(0.3)
                    result = sample_groups()
                    if any(isinstance(result[name], float) for name in timing):
                        break
            result = trigger_and_sample(result)
            return {name.lower(): result[name] for name in names}
        return {name.lower(): result[name] for name in names}
    finally:
        if sentinel is not None:
            scope.write(f":MEASure:SIMPle:ITEM {sentinel},OFF")
        scope.write(f":MEASure:SIMPle:SOURce {old_source}")
        if old_display.upper() != "ON":
            scope.write(f":MEASure {old_display}")


def _measurement_value_available(value: str) -> bool:
    return "number of measurements is zero" not in value.lower()


def _prepare_measurement(scope: LinuxUsbtmc, args) -> dict[str, str]:
    def quantity(value: str, units: dict[str, float]) -> float:
        match = re.fullmatch(
            r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z]*)\s*",
            value,
        )
        if not match or match.group(2).upper() not in units:
            raise ProtocolError(f"invalid expected quantity {value!r}")
        return float(match.group(1)) * units[match.group(2).upper()]

    def ceil_125(value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ProtocolError("expected frequency and peak-to-peak voltage must be positive")
        decade = 10.0 ** math.floor(math.log10(value))
        for step in (1.0, 2.0, 5.0, 10.0):
            candidate = step * decade
            if candidate >= value * (1.0 - 1e-12):
                return candidate
        raise AssertionError("unreachable")

    vertical_scale = args.vertical_scale
    if vertical_scale is None and args.expect_pkpk:
        pkpk = quantity(args.expect_pkpk, {"": 1.0, "V": 1.0, "VPP": 1.0, "MV": 1e-3, "MVPP": 1e-3})
        vertical_scale = f"{ceil_125(pkpk / 5.0):.12g}V"
    time_scale = args.time_scale
    if time_scale is None and args.expect_frequency:
        frequency = quantity(args.expect_frequency, {"": 1.0, "HZ": 1.0, "KHZ": 1e3, "MHZ": 1e6})
        time_scale = f"{ceil_125((1.0 / frequency) / 5.0):.12g}S"
    expected_offset = None
    if args.expect_offset:
        expected_offset = quantity(args.expect_offset, {"": 1.0, "V": 1.0, "MV": 1e-3, "UV": 1e-6})
    coupling = args.coupling or ("DC" if any((args.expect_frequency, args.expect_pkpk, args.expect_offset)) else None)
    requested = {
        "vertical_scale": vertical_scale,
        "time_scale": time_scale,
        "coupling": coupling,
        "offset": expected_offset,
    }
    if not any(value is not None for value in requested.values()):
        return {}
    source = args.source.upper()
    match = re.fullmatch(r"C([1-4])", source)
    if match is None:
        raise ProtocolError("measurement setup options require a physical C1..C4 source")
    channel = match.group(1)
    commands = [(f":CHANnel{channel}:SWITch", "ON")]
    if coupling:
        commands.append((f":CHANnel{channel}:COUPling", coupling))
    if vertical_scale:
        commands.append((f":CHANnel{channel}:SCALe", vertical_scale))
    if expected_offset is not None:
        commands.append((f":CHANnel{channel}:OFFSet", f"{-expected_offset:.12g}V"))
    if time_scale:
        commands.append((":TIMebase:SCALe", time_scale))
    result: dict[str, str] = {}
    for command, value in commands:
        scope.write(f"{command} {value}")
        actual = scope.query_text(command + "?")
        if not set_values_equivalent([value], actual):
            raise ProtocolError(f"measurement setup {command} requested {value!r}, readback is {actual!r}")
        result[command] = actual
    return result


def _parse_identity(response: str) -> tuple[str, str, str, str]:
    fields = tuple(field.strip() for field in response.split(","))
    if len(fields) < 4 or any(not field for field in fields[:4]):
        raise ProtocolError(f"invalid or empty *IDN? response: {response!r}")
    return fields[0], fields[1], fields[2], fields[3]


def _recover(args) -> dict[str, object]:
    if args.attempts <= 0:
        raise ProtocolError("recover attempts must be positive")
    if args.delay < 0:
        raise ProtocolError("recover delay cannot be negative")
    device = choose_device(args.device, args.serial)
    errors: list[str] = []

    def probe() -> tuple[str, str, str, str] | None:
        for attempt in range(args.attempts):
            try:
                with LinuxUsbtmc(
                    device,
                    timeout_ms=args.timeout or 3000,
                    clear_on_open=True,
                    command_delay_ms=args.command_delay,
                ) as scope:
                    return _parse_identity(scope.query_text("*IDN?"))
            except Sds824Error as exc:
                errors.append(str(exc))
                if attempt + 1 < args.attempts and args.delay:
                    time.sleep(args.delay)
        return None

    identity = probe()
    method = "usbtmc-clear"
    usb_node: str | None = None
    if identity is None and args.usb_reset:
        original_serial = device.serial
        usb_node = str(reset_usb_device(device))
        device = None
        for attempt in range(args.attempts):
            if args.delay:
                time.sleep(args.delay)
            try:
                device = choose_device(serial=original_serial or args.serial)
                break
            except TransportError as exc:
                errors.append(str(exc))
                if attempt + 1 == args.attempts:
                    raise TransportError(
                        "USB reset completed but the instrument did not re-enumerate"
                    ) from exc
        assert device is not None
        identity = probe()
        method = "usb-reset"
    if identity is None:
        detail = errors[-1] if errors else "no identity response"
        raise TransportError(f"instrument recovery failed: {detail}")
    return {
        "recovered": True,
        "method": method,
        "manufacturer": identity[0],
        "model": identity[1],
        "serial": identity[2],
        "firmware": identity[3],
        "usb_node": usb_node,
        "failed_probes": len(errors),
    }


def _capture_waveform(scope: LinuxUsbtmc, args) -> Waveform:
    old = {name: scope.query_text(command) for name, command in (
        ("source", ":WAVeform:SOURce?"), ("width", ":WAVeform:WIDTh?"),
        ("byteorder", ":WAVeform:BYTeorder?"), ("start", ":WAVeform:STARt?"),
        ("interval", ":WAVeform:INTerval?"), ("points", ":WAVeform:POINt?"),
    )}
    status = scope.query_text(":TRIGger:STATus?")
    resume = args.stop and status.upper() not in {"STOP", "STOPPED"}
    try:
        if args.stop:
            scope.write(":TRIGger:STOP")
        scope.write(f":WAVeform:SOURce {args.source.upper()}")
        scope.write(f":WAVeform:WIDTh {args.width}")
        scope.write(":WAVeform:BYTeorder LSB")
        scope.write(f":WAVeform:STARt {args.start}")
        scope.write(f":WAVeform:INTerval {args.interval}")
        if args.points is not None:
            scope.write(f":WAVeform:POINt {args.points}")
        # On SDS824 firmware 4.8.12.1.1.6.5, PREamble? changes the following
        # DATA? transfer back to the 2 kpoint display record even when
        # WAVeform:POINt? still reports the requested deep-memory count.
        # Read DATA first as shown in the programming-guide reconstruction
        # example, then fetch the descriptor that describes that transfer.
        raw = parse_ieee_block(scope.query(":WAVeform:DATA?"))
        preamble = parse_preamble(scope.query(":WAVeform:PREamble?"))
        if len(raw) % preamble.bytes_per_point:
            raise ProtocolError(f"waveform byte count {len(raw)} is not aligned to {preamble.bytes_per_point}-byte samples")
        return Waveform(args.source.upper(), preamble, raw)
    finally:
        for name, command in (
            ("source", ":WAVeform:SOURce"), ("width", ":WAVeform:WIDTh"),
            ("byteorder", ":WAVeform:BYTeorder"), ("start", ":WAVeform:STARt"),
            ("interval", ":WAVeform:INTerval"), ("points", ":WAVeform:POINt"),
        ):
            scope.write(f"{command} {old[name]}")
        if resume:
            scope.write(":TRIGger:RUN")


def _write_response(data: bytes, output: Path | None, binary: bool) -> None:
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    elif binary:
        sys.stdout.buffer.write(data)
    else:
        try:
            print(data.decode("ascii").strip())
        except UnicodeDecodeError as exc:
            raise ProtocolError("binary response requires --binary or --output") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(_protect_negative_values(raw_argv))
    _restore_negative_values(args)
    try:
        if args.command == "list":
            for item in discover_devices():
                print(f"{item.path} usb={item.vendor_id}:{item.product_id} serial={item.serial or '-'} product={item.product or '-'}")
            return 0
        if args.command == "commands":
            if args.commands_command == "audit":
                sections = sorted({item.section for item in COMMANDS}, key=lambda x: tuple(map(int, x.split('.'))))
                print(json.dumps({
                    "manual_command_blocks": len(COMMANDS),
                    "unique_names": len({item.name for item in COMMANDS}),
                    "query_capable": sum(item.can_query for item in COMMANDS),
                    "write_capable": sum(item.can_write for item in COMMANDS),
                    "sections": {section: sum(item.section == section for item in COMMANDS) for section in sections},
                }, indent=2))
                return 0
            if args.commands_command == "list":
                for spec in COMMANDS:
                    if args.section and args.section.lower() not in (spec.section + " " + spec.section_title).lower():
                        continue
                    if args.queryable and not spec.can_query:
                        continue
                    if args.writable and not spec.can_write:
                        continue
                    print(f"{spec.name:52} {spec.kind:9} {spec.support_class:11} {spec.template}")
                return 0
            spec = get_command(args.name)
            access = [name for name, enabled in (("query", spec.can_query), ("set", spec.can_write)) if enabled]
            if not access:
                access = [spec.kind]
            core = {
                "name": spec.name,
                "format": spec.formats[0] if spec.formats else spec.template,
                "access": access,
            }
            if not args.verbose and not args.json:
                print(f"{core['name']}  {core['format']}  {','.join(access)}")
                return 0
            payload = (
                asdict(spec) | {
                    "kind": spec.kind,
                    "support_class": spec.support_class,
                    "placeholders": spec.placeholders,
                }
                if args.verbose else core
            )
            print(json.dumps(
                payload,
                ensure_ascii=False,
                indent=2 if args.pretty or (args.verbose and not args.json) else None,
                separators=None if args.pretty or (args.verbose and not args.json) else (",", ":"),
            ))
            return 0

        if args.command == "recover":
            print(json.dumps(_recover(args), indent=2))
            return 0

        if args.command in {"get", "set", "action"}:
            spec = get_command(args.name)
            if spec.support_class != "sds824" and not args.allow_unsupported:
                raise ProtocolError(
                    f"{spec.name} is classified {spec.support_class}; repeat with --allow-unsupported only if the required model/option is present"
                )
            command = render_command(spec, _indices(args))
            if args.command == "get":
                if not spec.can_query:
                    raise ProtocolError(f"{spec.name} is not queryable")
                formatted = _format_scpi_arguments(spec, args.values, query=True)
                suffix = (" " + formatted) if formatted else ""
                with _session(args) as scope:
                    _write_response(scope.query(command + "?" + suffix, max_bytes=args.max_bytes), args.output, args.binary)
                return 0
            if args.command == "set":
                if not spec.can_write or spec.kind == "action":
                    raise ProtocolError(f"{spec.name} is not settable")
                validate_set_values(spec, args.values)
                with _session(args) as scope:
                    scope.write(
                        command + " " + _format_scpi_arguments(spec, args.values)
                    )
                    if not args.no_verify and can_verify_set(spec, args.values):
                        readback = scope.query_text(command + "?")
                        if not set_values_equivalent(args.values, readback, spec):
                            raise ProtocolError(
                                f"{spec.name} rejected or normalized {args.values!r}; readback is {readback!r}"
                            )
                return 0
            if spec.kind != "action":
                raise ProtocolError(f"{spec.name} is not an action; use set")
            if spec.name in DESTRUCTIVE_ACTIONS and not args.yes:
                raise ProtocolError(f"{spec.name} broadly changes state; repeat with --yes")
            with _session(args) as scope:
                formatted = _format_scpi_arguments(spec, args.values)
                scope.write(command + ((" " + formatted) if formatted else ""))
            return 0

        with _session(args) as scope:
            if args.command == "info":
                fields = _parse_identity(scope.query_text("*IDN?"))
                print(json.dumps({
                    "manufacturer": fields[0],
                    "model": fields[1],
                    "serial": fields[2],
                    "firmware": fields[3],
                    "device": str(scope.device.path),
                    "usb": f"{scope.device.vendor_id}:{scope.device.product_id}",
                }, indent=2))
                return 0
            if args.command == "config":
                print(json.dumps(_query_snapshot(scope), indent=2))
                return 0
            if args.command == "raw":
                read = args.read or "?" in args.scpi.split(" ", 1)[0]
                if read:
                    _write_response(scope.query(args.scpi, max_bytes=args.max_bytes), args.output, args.binary)
                else:
                    scope.write(args.scpi)
                return 0
            if args.command == "batch":
                if str(args.file) == "-":
                    return _run_batch(scope, sys.stdin)
                with args.file.open() as stream:
                    return _run_batch(scope, stream)
            if args.command == "measure":
                setup = _prepare_measurement(scope, args)
                raw_values = _measure(
                    scope,
                    args.metrics,
                    args.source,
                    voltage_autorange=args.vertical_scale is None,
                    time_autorange=args.time_scale is None,
                )
                unavailable = {
                    name: value for name, value in raw_values.items()
                    if isinstance(value, str) and not value.strip().strip("*")
                }
                values = raw_values if args.include_unavailable else {
                    name: value for name, value in raw_values.items() if name not in unavailable
                }
                if args.json or args.metrics == ["all"]:
                    payload = {"source": args.source.upper(), "measurements": values}
                    if setup:
                        payload["setup"] = setup
                    if unavailable and not args.include_unavailable:
                        payload["unavailable"] = len(unavailable)
                    print(json.dumps(payload, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
                else:
                    print(" ".join(str(value) for value in raw_values.values()))
                return 0
            if args.command == "screenshot":
                style = "INVerted" if args.inverted else "NORMal"
                data = scope.query(
                    f":PRINt? {args.format.upper()},{style}",
                    retries=args.retries,
                    retry_delay_ms=args.retry_delay * 1000,
                )
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(data.rstrip(b"\n") if args.format == "png" else data[:int.from_bytes(data[2:6], 'little')])
                return 0
            if args.command == "waveform":
                waveform = _capture_waveform(scope, args)
                write_waveform(waveform, args.output, args.format)
                return 0
        parser.error(f"unsupported command {args.command}")
    except (Sds824Error, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

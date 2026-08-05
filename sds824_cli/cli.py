from __future__ import annotations

import argparse
import json
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

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
    parser.add_argument("--no-clear", action="store_true", help="do not issue USBTMC CLEAR when opening")


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

    measure = sub.add_parser("measure", help="read one or all simple measurements")
    measure.add_argument("metric", choices=[x.lower() for x in MEASURE_TYPES] + ["all"])
    measure.add_argument("--source", default="C1", help="C1, C2, F1, M1, etc.")
    measure.add_argument("--json", action="store_true")

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
    with LinuxUsbtmc(device, timeout_ms=timeout_ms, clear_on_open=not args.no_clear,
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


def _measure(scope: LinuxUsbtmc, metric: str, source: str) -> dict[str, str | float]:
    source = source.upper()
    if not re.fullmatch(r"(?:C[1-4]|F\d+|M\d+|REF[ABCD])", source):
        raise ProtocolError(f"unsupported simple measurement source {source!r}")
    requested = metric.upper()
    if requested in SDS824_UNSUPPORTED_MEASURE_TYPES:
        raise ProtocolError(
            f"{requested} is documented for the series but times out on the tested SDS824 firmware"
        )
    old_display = scope.query_text(":MEASure?")
    old_source = scope.query_text(":MEASure:SIMPle:SOURce?")
    names = (
        tuple(name for name in MEASURE_TYPES if name not in SDS824_UNSUPPORTED_MEASURE_TYPES)
        if metric == "all" else (requested,)
    )
    sentinel: str | None = None
    try:
        if old_display.upper() != "ON":
            scope.write(":MEASure ON")
        scope.write(f":MEASure:SIMPle:SOURce {source}")
        probe = scope.query_text(f":MEASure:SIMPle:VALue? {names[0]}")
        if not _measurement_value_available(probe):
            sentinel = names[0]
            scope.write(f":MEASure:SIMPle:ITEM {sentinel},ON")
        time.sleep(0.2)
        result: dict[str, str | float] = {}
        for name in names:
            value = scope.query_text(f":MEASure:SIMPle:VALue? {name}")
            try:
                result[name.lower()] = float(value)
            except ValueError:
                result[name.lower()] = value
        return result
    finally:
        if sentinel is not None:
            scope.write(f":MEASure:SIMPle:ITEM {sentinel},OFF")
        scope.write(f":MEASure:SIMPle:SOURce {old_source}")
        if old_display.upper() != "ON":
            scope.write(f":MEASure {old_display}")


def _measurement_value_available(value: str) -> bool:
    return "number of measurements is zero" not in value.lower()


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
            print(json.dumps(asdict(spec) | {"kind": spec.kind, "support_class": spec.support_class, "placeholders": spec.placeholders}, ensure_ascii=False, indent=2))
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
                values = _measure(scope, args.metric, args.source)
                if args.json or args.metric == "all":
                    print(json.dumps({"source": args.source.upper(), "measurements": values}, indent=2))
                else:
                    print(next(iter(values.values())))
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
                print(json.dumps({"format": args.format, "bytes": args.output.stat().st_size, "output": str(args.output)}))
                return 0
            if args.command == "waveform":
                waveform = _capture_waveform(scope, args)
                write_waveform(waveform, args.output, args.format)
                print(json.dumps({
                    "source": waveform.source,
                    "requested_points": args.points,
                    "points": waveform.point_count,
                    "format": args.format,
                    "output": str(args.output),
                    "sample_interval": waveform.preamble.sample_interval,
                    "effective_sample_interval": (
                        waveform.preamble.sample_interval * waveform.preamble.interval
                    ),
                }))
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

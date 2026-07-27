#!/usr/bin/env python3
"""State-restoring SDS824 parameter matrix derived from the CN11G guide.

Only unambiguous enumeration matrices are generated automatically.  Contextual
trigger families are selected before testing their child settings.  Every queried
original value is restored, and a failed *IDN? health probe halts the run.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

from sds824_cli.catalog import COMMANDS, CommandSpec, render_command
from sds824_cli.errors import Sds824Error
from sds824_cli.parameters import declared_enums, write_argument_names
from sds824_cli.transport import LinuxUsbtmc, choose_device

INDICES = {"n": 1, "x": 1, "m": 1, "r": "A", "d": 0, "channel": "C1"}
TRIGGER_CONTEXT = {
    "trigger.edge.": "EDGE", "trigger.slope.": "SLOPe", "trigger.pulse.": "PULSe",
    "trigger.video.": "VIDeo", "trigger.window.": "WINDow", "trigger.interval.": "INTerval",
    "trigger.dropout.": "DROPout", "trigger.runt.": "RUNT", "trigger.pattern.": "PATTern",
    "trigger.qualified.": "QUALified", "trigger.delay.": "DELay", "trigger.nedge.": "NEDGe",
    "trigger.shold.": "SHOLd", "trigger.iic.": "IIC", "trigger.spi.": "SPI",
    "trigger.uart.": "UART", "trigger.can.": "CAN", "trigger.lin.": "LIN",
}
GROUP_SECTIONS = {
    "core": {"5.3", "5.4", "5.9", "5.13", "5.20", "5.21", "5.23"},
    "function": {"5.11"},
    "trigger": {"5.22"},
    "decode": {"5.7"},
}
# Optional/licensed protocols are cataloged but intentionally not probed until
# the corresponding option is known present; an unsupported query can wedge the
# firmware's remote-control service and require a power cycle.
UNSAFE_OPTION_PREFIXES = (
    "trigger.flexray.", "trigger.canfd.", "trigger.iis.", "trigger.sent.",
    "decode.bus.n.flexray.", "decode.bus.n.canfd.", "decode.bus.n.iis.",
    "decode.bus.n.m1553.", "decode.bus.n.sent.", "decode.bus.n.manchester.",
)
# Broad modes/options that change unrelated configuration or need external modules.
EXCLUDE = {
    "acquire.mode",  # XY/ROLL require distinct timebase/channel contexts
    "acquire.mmanagement", "acquire.sequence", "root.measure",
    "system.communicate.lan.type", "system.nstorage.type", "system.lock",
    "trigger.type",  # covered explicitly by --group trigger type matrix below
    "waveform.source", "waveform.width", "waveform.byteorder",
}
NUMERIC_MATRICES = {
    "display.backlight": ["20", "50", "100"],
    "display.graticule": ["0", "50", "100"],
    "display.intensity": ["0", "50", "100"],
    "display.transparence": ["0", "50", "100"],
    "channel.n.skew": ["-1E-7", "0", "1E-7"],
    "channel.n.offset": ["-1", "0", "1"],
    "channel.n.scale": ["0.001", "0.002", "0.005", "0.01", "0.02", "0.05", "0.1", "0.2", "0.5", "1"],
    "timebase.scale": ["1E-9", "2E-9", "5E-9", "10E-9", "100E-9", "1E-6", "10E-6", "100E-6", "1E-3", "10E-3", "100E-3", "1"],
    "trigger.edge.level": ["-1", "0", "1"],
    "trigger.edge.hldtime": ["8E-9", "1E-6", "1E-3", "1"],
}


def simple_options(spec: CommandSpec) -> list[str]:
    names = write_argument_names(spec)
    enums = declared_enums(spec)
    if len(names) != 1 or names[0] not in enums:
        return NUMERIC_MATRICES.get(spec.name, [])
    options = list(enums[names[0]])
    if any(any(char in option for char in "<[]> ,") for option in options):
        return NUMERIC_MATRICES.get(spec.name, [])
    return options


def trigger_type_for(spec: CommandSpec) -> str | None:
    for prefix, value in TRIGGER_CONTEXT.items():
        if spec.name.startswith(prefix):
            return value
    return None


def applicable(spec: CommandSpec, group: str) -> bool:
    if spec.section not in GROUP_SECTIONS[group] or not (spec.can_query and spec.can_write):
        return False
    if spec.name in EXCLUDE or spec.optional_marked or spec.name.startswith(UNSAFE_OPTION_PREFIXES):
        return False
    if group == "decode" and not any(f".{proto}." in spec.name for proto in ("iic", "spi", "uart", "can", "lin")):
        return False
    return bool(simple_options(spec))


def expanded_indices(spec: CommandSpec) -> list[dict]:
    if spec.name.startswith("channel.n."):
        return [INDICES | {"n": 1}, INDICES | {"n": 2}]
    return [INDICES]


def equivalent(request: str, response: str) -> bool:
    request = request.strip().upper()
    response = response.strip().upper()
    if response == request:
        return True
    # Instruments normally return the long enum for an accepted abbreviation.
    return response.startswith(request) or request.startswith(response)


def query(scope: LinuxUsbtmc, command: str) -> str:
    return scope.query_text(command + "?")


def run_matrix(scope: LinuxUsbtmc, spec: CommandSpec, indices: dict, values: list[str]) -> list[dict]:
    path = render_command(spec, indices)
    context = trigger_type_for(spec)
    original_trigger = None
    if context:
        original_trigger = scope.query_text(":TRIGger:TYPE?")
        scope.write(f":TRIGger:TYPE {context}")
    original = query(scope, path)
    results = []
    try:
        for value in values:
            started = time.monotonic()
            scope.write(f"{path} {value}")
            readback = query(scope, path)
            results.append({
                "value": value, "readback": readback,
                "accepted": equivalent(value.split(",", 1)[0], readback.split(",", 1)[0]),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            })
    finally:
        scope.write(f"{path} {original}")
        if original_trigger is not None:
            scope.write(f":TRIGger:TYPE {original_trigger}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=tuple(GROUP_SECTIONS) + ("trigger-types",))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-ms", type=int, default=3000)
    args = parser.parse_args()
    output = args.output or Path(f"validation/matrix-{args.group}.json")
    device = choose_device()
    report = {
        "timestamp": datetime.now().astimezone().isoformat(), "group": args.group,
        "instrument": None, "complete": False, "matrices": [], "error": None,
    }
    try:
        with LinuxUsbtmc(device, timeout_ms=args.timeout_ms, command_delay_ms=20) as scope:
            report["instrument"] = scope.query_text("*IDN?")
            if args.group == "trigger-types":
                original = scope.query_text(":TRIGger:TYPE?")
                values = ["EDGE", "PULSe", "SLOPe", "INTerval", "PATTern", "RUNT", "WINDow", "DROPout", "VIDeo", "QUALified", "NEDGe", "DELay", "SHOLd", "IIC", "SPI", "UART", "LIN", "CAN"]
                try:
                    result = []
                    for value in values:
                        scope.write(f":TRIGger:TYPE {value}")
                        readback = scope.query_text(":TRIGger:TYPE?")
                        result.append({"value": value, "readback": readback, "accepted": equivalent(value, readback)})
                    report["matrices"].append({"name": "trigger.type", "values": result})
                finally:
                    scope.write(f":TRIGger:TYPE {original}")
            else:
                specs = [spec for spec in COMMANDS if applicable(spec, args.group)]
                for spec in specs:
                    for indices in expanded_indices(spec):
                        values = simple_options(spec)
                        record = {"name": spec.name, "path": render_command(spec, indices), "indices": {key: indices[key] for key in spec.placeholders}, "declared_values": values}
                        try:
                            record["values"] = run_matrix(scope, spec, indices, values)
                            record["complete"] = True
                        except (Sds824Error, OSError) as exc:
                            record["complete"] = False
                            record["error"] = str(exc)
                            report["matrices"].append(record)
                            raise
                        report["matrices"].append(record)
                        print(f"{len(report['matrices']):3} {record['path']} ({len(values)})", flush=True)
            report["complete"] = True
    except (Sds824Error, OSError) as exc:
        report["error"] = str(exc)
    report["summary"] = {
        "matrices": len(report["matrices"]),
        "values": sum(len(item.get("values", [])) for item in report["matrices"]),
        "accepted": sum(sum(bool(value.get("accepted")) for value in item.get("values", [])) for item in report["matrices"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"]))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Connected, non-destructive command and parameter audit for the SDS824.

The query sweep sends every query-capable programming-guide command.  It uses one
representative index for templated paths and records exact response/error evidence.
Writes and actions are exercised by the separate state-restoring parameter matrix.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from sds824_cli.catalog import COMMANDS, render_command
from sds824_cli.errors import Sds824Error
from sds824_cli.transport import LinuxUsbtmc, choose_device

DEFAULT_INDICES = {"n": 1, "x": 1, "m": 1, "r": "A", "d": 0, "channel": "C1"}
QUERY_ARGS = {
    "root.print": "PNG,NORMal",
    "measure.advanced.p.n.statistics": "ALL",
    "measure.simple.value": "FREQ",
    "trigger.pattern.level": "C1",
}
SLOW = {"root.print", "waveform.data", "waveform.preamble", "decode.list.n.result", "decode.bus.n.result"}


def response_record(data: bytes) -> dict:
    record = {"bytes": len(data), "head_hex": data[:32].hex()}
    try:
        text = data.decode("ascii").strip()
        record["response"] = text if len(text) <= 1000 else text[:1000] + "…"
    except UnicodeDecodeError:
        record["binary"] = True
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("validation/query-audit.json"))
    parser.add_argument("--timeout-ms", type=int, default=750)
    parser.add_argument("--start", type=int, default=0)
    args = parser.parse_args()
    device = choose_device()
    results = []
    halted_reason = None
    query_specs = [spec for spec in COMMANDS if spec.can_query]
    for number, spec in enumerate(query_specs):
        if number < args.start:
            continue
        command = render_command(spec, DEFAULT_INDICES) + "?"
        if spec.name in QUERY_ARGS:
            command += " " + QUERY_ARGS[spec.name]
        timeout = 5000 if spec.name in SLOW else args.timeout_ms
        started = time.monotonic()
        record = {
            "ordinal": number,
            "name": spec.name,
            "section": spec.section,
            "command": command,
            "placeholders": {key: DEFAULT_INDICES[key] for key in spec.placeholders},
        }
        try:
            with LinuxUsbtmc(device, timeout_ms=timeout, command_delay_ms=0) as scope:
                data = scope.query(command, max_bytes=128 * 1024 * 1024)
            record.update(response_record(data))
            record["status"] = "response" if data else "empty"
        except (Sds824Error, OSError) as exc:
            record["status"] = "error"
            record["error"] = str(exc)
        record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        results.append(record)
        print(f"{number + 1:3}/{len(query_specs)} {record['status']:8} {spec.name}", flush=True)
        if record["status"] == "error":
            time.sleep(0.5)
            try:
                with LinuxUsbtmc(device, timeout_ms=2000, command_delay_ms=0) as health:
                    health.query_text("*IDN?")
            except (Sds824Error, OSError) as exc:
                halted_reason = f"health probe failed after {spec.name}: {exc}"
                print("HALT:", halted_reason, flush=True)
                break
    report = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "instrument": None,
        "device": str(device.path),
        "manual_command_blocks": len(COMMANDS),
        "query_capable": len(query_specs),
        "tested": len(results),
        "complete": len(results) == len(query_specs) and halted_reason is None,
        "halted_reason": halted_reason,
        "counts": {status: sum(item["status"] == status for item in results) for status in ("response", "empty", "error")},
        "results": results,
    }
    try:
        with LinuxUsbtmc(device, timeout_ms=2000, command_delay_ms=0) as scope:
            report["instrument"] = scope.query_text("*IDN?")
    except (Sds824Error, OSError) as exc:
        report["final_health_error"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

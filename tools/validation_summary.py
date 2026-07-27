#!/usr/bin/env python3
"""Consolidate completed connected matrices into one auditable device profile."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sds824_cli.catalog import COMMANDS
from sds824_cli.cli import SDS824_UNSUPPORTED_MEASURE_TYPES
from sds824_cli.parameters import SDS824_NUMERIC_RANGES, SDS824_UNSUPPORTED_ENUMS

MATRIX_GROUPS = ("core", "function", "trigger-types", "trigger", "decode")


def rejection_is_profiled(name: str, value: str) -> bool:
    upper = value.upper()
    if upper in SDS824_UNSUPPORTED_ENUMS.get(name, set()):
        return True
    if name in SDS824_NUMERIC_RANGES:
        low, high = SDS824_NUMERIC_RANGES[name]
        try:
            return not low <= float(value) <= high
        except ValueError:
            return False
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-dir", type=Path, default=Path("validation"))
    parser.add_argument("--output", type=Path, default=Path("validation/device-profile.json"))
    args = parser.parse_args()

    groups = {}
    rejections = []
    for group in MATRIX_GROUPS:
        report = json.loads((args.validation_dir / f"matrix-{group}.json").read_text())
        if not report.get("complete"):
            raise SystemExit(f"matrix {group} is incomplete")
        groups[group] = report["summary"]
        for matrix in report["matrices"]:
            for value in matrix.get("values", []):
                if not value.get("accepted"):
                    rejection = {
                        "name": matrix["name"],
                        "path": matrix.get("path"),
                        "value": value["value"],
                        "readback": value["readback"],
                    }
                    rejection["profiled"] = rejection_is_profiled(
                        rejection["name"], rejection["value"]
                    )
                    rejections.append(rejection)
    if not all(item["profiled"] for item in rejections):
        raise SystemExit("one or more connected rejections are absent from the CLI profile")

    report = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "instrument": json.loads(
            (args.validation_dir / "matrix-core.json").read_text()
        )["instrument"],
        "complete": True,
        "catalog": {
            "manual_command_blocks": len(COMMANDS),
            "unique_names": len({item.name for item in COMMANDS}),
            "query_capable": sum(item.can_query for item in COMMANDS),
            "write_capable": sum(item.can_write for item in COMMANDS),
            "support_classes": {
                kind: sum(item.support_class == kind for item in COMMANDS)
                for kind in ("sds824", "optional", "other-model")
            },
        },
        "connected_matrices": {
            "groups": groups,
            "matrices": sum(item["matrices"] for item in groups.values()),
            "values": sum(item["values"] for item in groups.values()),
            "accepted": sum(item["accepted"] for item in groups.values()),
            "rejected_or_normalized": len(rejections),
        },
        "profiled_rejections": rejections,
        "unsupported_measurements": sorted(SDS824_UNSUPPORTED_MEASURE_TYPES),
        "numeric_ranges": {
            name: {"minimum": limits[0], "maximum": limits[1]}
            for name, limits in SDS824_NUMERIC_RANGES.items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["connected_matrices"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

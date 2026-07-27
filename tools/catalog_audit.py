#!/usr/bin/env python3
"""Rebuild and audit the complete CN11G catalog against the packaged artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from sds824_cli.catalog import COMMANDS, render_command

INDICES = {"n": 1, "x": 1, "m": 1, "r": "A", "d": 0, "channel": "C1"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=Path("docs/official/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf"))
    parser.add_argument("--catalog", type=Path, default=Path("sds824_cli/manual_catalog.json"))
    parser.add_argument("--output", type=Path, default=Path("validation/catalog-audit.json"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as directory:
        regenerated = Path(directory) / "catalog.json"
        subprocess.run([
            sys.executable, "tools/extract_manual_catalog.py", str(args.pdf), str(regenerated)
        ], check=True, stdout=subprocess.PIPE, text=True)
        source_data = json.loads(regenerated.read_text())
    packaged_data = json.loads(args.catalog.read_text())
    exact_match = source_data == packaged_data

    rendered = []
    errors = []
    for spec in COMMANDS:
        try:
            path = render_command(spec, INDICES)
            if any(character in path for character in "<>{}[]"):
                raise ValueError(f"unresolved syntax in {path}")
            rendered.append(spec.name)
        except Exception as exc:  # audit must preserve all evidence
            errors.append({"name": spec.name, "error": str(exc)})

    firmware_matches = [
        spec.name for spec in COMMANDS
        if any(word in (spec.name + " " + spec.heading + " " + spec.description).lower()
               for word in ("firmware update", "firmware upgrade", "bootloader", "reflash"))
    ]
    sections = Counter(spec.section for spec in COMMANDS)
    support = Counter(spec.support_class for spec in COMMANDS)
    report = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "source_pdf": str(args.pdf),
        "source_pdf_sha256": sha256(args.pdf),
        "catalog": str(args.catalog),
        "catalog_sha256": sha256(args.catalog),
        "regenerated_exact_match": exact_match,
        "manual_command_blocks": len(COMMANDS),
        "unique_names": len({spec.name for spec in COMMANDS}),
        "unique_headings": len({spec.heading for spec in COMMANDS}),
        "rendered_templates": len(rendered),
        "render_errors": errors,
        "query_capable": sum(spec.can_query for spec in COMMANDS),
        "write_capable": sum(spec.can_write for spec in COMMANDS),
        "sections": dict(sorted(sections.items(), key=lambda item: tuple(map(int, item[0].split("."))))),
        "support_classes": dict(sorted(support.items())),
        "firmware_command_matches": firmware_matches,
        "firmware_policy": "Firmware upgrade/reflash is excluded; CN11G contains no matching command block.",
        "complete": exact_match and len(COMMANDS) == 712 and len(rendered) == 712 and not errors and not firmware_matches,
        "commands": [
            {
                "name": spec.name, "heading": spec.heading, "section": spec.section,
                "kind": spec.kind, "support_class": spec.support_class,
                "template": spec.template, "formats": list(spec.formats), "pdf_page": spec.pdf_page,
            }
            for spec in COMMANDS
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "complete", "manual_command_blocks", "unique_names", "rendered_templates",
        "query_capable", "write_capable", "support_classes",
    )}, ensure_ascii=False, indent=2))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

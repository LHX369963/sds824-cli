#!/usr/bin/env python3
"""Extract the command headings and declared syntax from the official PDF.

This is an audit tool, not a general PDF parser.  It deliberately fails if the
known SDS programming-guide layout changes instead of silently dropping entries.
Requires the Poppler ``pdftotext`` command.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

HEADING = re.compile(
    r"^(?:\*|:|\[?SENSe|CONFigure|MEASure|READ|FETCh|ARbWaVe|BaSic_WaVe|OUTPut|SToreList|SYNC|VOLTPRT|MMETer)[^\s?]*(?:（选配）)?$"
)
SECTION = re.compile(r"^5\.(\d+)\s+(.+?)\s*$")
LABELS = ("描述", "命令格式", "参数说明", "返回格式", "示例", "关联命令", "注意")
MODEL_RE = re.compile(r"SDS(?:7000A|6000(?:L|A| Pro)?|5000X|3000X HD|2000X(?: HD| Plus)?|1000X HD|800X HD)|SHS(?:800X|1000X)", re.I)


def clean_inline(value: str) -> str:
    return " ".join(value.replace("\u3000", " ").split())


def extract_field(block: list[str], label: str) -> str:
    found = False
    out: list[str] = []
    for line in block:
        stripped = line.strip()
        if not found:
            if stripped.startswith(label):
                found = True
                tail = stripped[len(label):].strip()
                if tail:
                    out.append(tail)
            continue
        if any(stripped.startswith(other) for other in LABELS if other != label):
            break
        if stripped.startswith("www.siglent.com") or stripped == "SDS 系列编程手册":
            continue
        if stripped:
            out.append(stripped)
    return clean_inline(" ".join(out))


def extract_formats(block: list[str]) -> list[str]:
    label_index = next((i for i, line in enumerate(block) if "命令格式" in line), None)
    if label_index is None:
        return []
    start = next((i for i, line in enumerate(block[:label_index + 1]) if line.strip().startswith("描述")), 1)
    end = len(block)
    for i in range(label_index + 1, len(block)):
        stripped = block[i].strip()
        if any(stripped.startswith(label) for label in LABELS if label != "命令格式"):
            end = i
            break
    formats: list[str] = []
    for i in range(start, end):
        stripped = block[i].strip()
        if "命令格式" in stripped:
            stripped = stripped.split("命令格式", 1)[1].strip()
        if not stripped or stripped.startswith("www.siglent.com") or stripped == "SDS 系列编程手册":
            continue
        if re.match(r"^(?:<channel>:|\*|:|\[?SENSe|CONFigure|MEASure|READ|FETCh|StoreList|SToreList|SYNC|VOLTPRT|MMETer)", stripped):
            candidate = clean_inline(stripped)
            if not re.search(r"[\u3400-\u9fff]", candidate) and candidate not in formats:
                formats.append(candidate)
    return formats


def strip_optional_scpi(command: str) -> str:
    # Brackets denote an optional keyword.  The catalog uses the explicit form.
    return command.replace("[", "").replace("]", "")


def command_template(heading: str) -> str:
    if heading in {"ARbWaVe", "BaSic_WaVe", "OUTPut", "SYNC"}:
        return "{channel}:" + heading
    value = heading.replace("（选配）", "")
    value = strip_optional_scpi(value)
    value = re.sub(r"<([^>]+)>", lambda m: "{" + re.sub(r"\W+", "_", m.group(1)).lower() + "}", value)
    return value


def command_name(heading: str) -> str:
    if heading in {"ARbWaVe", "BaSic_WaVe", "OUTPut", "SToreList", "SYNC", "VOLTPRT"}:
        return "wgen." + heading.lower().replace("_", "-")
    if heading == "MMETer":
        return "meter.mmeter"
    value = heading.replace("（选配）", "")
    value = strip_optional_scpi(value).lstrip(":*")
    pieces: list[str] = []
    for segment in value.split(":"):
        for text, placeholder in re.findall(r"([^<{]*)(?:<([^>]+)>)?", segment):
            if text:
                pieces.append(text.lower())
            if placeholder:
                pieces.append(re.sub(r"\W+", "-", placeholder).strip("-").lower())
    prefix = "ieee" if heading.startswith("*") else ("root" if ":" not in value else "")
    return ".".join(x for x in (prefix, *pieces) if x)


def parse_text(text: str) -> list[dict]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line == "5      命令与查询")
    end = next(i for i, line in enumerate(lines[start + 1:], start + 1) if re.match(r"6\s+编程实例", line))
    candidates = [i for i in range(start, end) if HEADING.match(lines[i])]
    sections: list[tuple[int, str, str]] = []
    for i in range(start, end):
        match = SECTION.match(lines[i])
        if match:
            sections.append((i, match.group(1), clean_inline(match.group(2))))
    entries: list[dict] = []
    for pos, line_index in enumerate(candidates):
        block_end = candidates[pos + 1] if pos + 1 < len(candidates) else end
        block = lines[line_index:block_end]
        formats = extract_formats(block)
        if not formats:
            continue
        section_line, section_number, section_title = max(item for item in sections if item[0] <= line_index)
        heading = lines[line_index]
        models = sorted(set(MODEL_RE.findall(" ".join(block))), key=str.lower)
        page = text[: sum(len(x) + 1 for x in lines[:line_index])].count("\f") + 1
        entries.append({
            "name": command_name(heading),
            "heading": heading.replace("（选配）", ""),
            "template": command_template(heading),
            "section": f"5.{section_number}",
            "section_title": section_title,
            "formats": formats,
            "can_query": any("?" in item.split(" ", 1)[0] for item in formats),
            "can_write": any("?" not in item.split(" ", 1)[0] for item in formats),
            "description": extract_field(block, "描述"),
            "parameters": extract_field(block, "参数说明"),
            "models_mentioned": models,
            "optional_marked": "选配" in heading or "选配" in section_title,
            "pdf_page": page,
            "text_line": line_index + 1,
        })
    names = [item["name"] for item in entries]
    headings = [item["heading"] for item in entries]
    if len(entries) != 712:
        raise RuntimeError(f"expected 712 command blocks from CN11G, extracted {len(entries)}")
    if len(names) != len(set(names)):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise RuntimeError(f"non-unique generated names: {duplicates}")
    if len(headings) != len(set(headings)):
        raise RuntimeError("manual headings unexpectedly duplicated")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        txt = Path(tmp) / "manual.txt"
        subprocess.run(["pdftotext", "-layout", str(args.pdf), str(txt)], check=True)
        entries = parse_text(txt.read_text(errors="replace"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"source": args.pdf.name, "command_count": len(entries), "commands": entries}, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(entries)} commands to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

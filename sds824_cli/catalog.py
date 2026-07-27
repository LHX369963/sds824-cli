from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Mapping

from .errors import ProtocolError


@dataclass(frozen=True)
class CommandSpec:
    name: str
    heading: str
    template: str
    section: str
    section_title: str
    formats: tuple[str, ...]
    can_query: bool
    can_write: bool
    description: str
    parameters: str
    models_mentioned: tuple[str, ...]
    optional_marked: bool
    pdf_page: int
    text_line: int

    @property
    def placeholders(self) -> tuple[str, ...]:
        return tuple(re.findall(r"\{([^}]+)\}", self.template))

    @property
    def kind(self) -> str:
        if self.can_query and self.can_write:
            return "query-set"
        if self.can_query:
            return "query"
        return "action"


def _load() -> tuple[CommandSpec, ...]:
    data = json.loads(files("sds824_cli").joinpath("manual_catalog.json").read_text())
    if data.get("command_count") != 705:
        raise RuntimeError("packaged programming-guide catalog is incomplete")
    return tuple(CommandSpec(
        name=item["name"], heading=item["heading"], template=item["template"],
        section=item["section"], section_title=item["section_title"],
        formats=tuple(item["formats"]), can_query=item["can_query"],
        can_write=item["can_write"], description=item["description"],
        parameters=item["parameters"], models_mentioned=tuple(item["models_mentioned"]),
        optional_marked=item["optional_marked"], pdf_page=item["pdf_page"],
        text_line=item["text_line"],
    ) for item in data["commands"])


COMMANDS = _load()
COMMAND_BY_NAME = {item.name: item for item in COMMANDS}


def get_command(name: str) -> CommandSpec:
    try:
        return COMMAND_BY_NAME[name]
    except KeyError as exc:
        raise ProtocolError(f"unknown command {name!r}; use 'sds824 commands list'") from exc


def render_command(spec: CommandSpec, values: Mapping[str, int | str | None]) -> str:
    rendered = spec.template
    for placeholder in spec.placeholders:
        value = values.get(placeholder)
        if value is None:
            raise ProtocolError(f"{spec.name} requires --{placeholder}")
        text = str(value)
        if not re.fullmatch(r"[A-Za-z0-9_+-]+", text):
            raise ProtocolError(f"invalid --{placeholder} value {text!r}")
        rendered = rendered.replace("{" + placeholder + "}", text)
    return rendered

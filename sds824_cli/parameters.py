from __future__ import annotations

import re

from .catalog import CommandSpec
from .errors import ProtocolError

_DEF = re.compile(r"<\s*([^>]+?)\s*>\s*:=\s*\{([^{}]+)\}")
_PLACEHOLDER = re.compile(r"<\s*([^>]+?)\s*>")


def declared_enums(spec: CommandSpec) -> dict[str, tuple[str, ...]]:
    """Return enum declarations recoverable without interpreting prose tables."""
    result: dict[str, tuple[str, ...]] = {}
    for match in _DEF.finditer(spec.parameters):
        name = re.sub(r"\s+", "", match.group(1)).lower()
        options = tuple(part.strip() for part in match.group(2).split("|") if part.strip())
        if options:
            result[name] = options
    return result


def write_argument_names(spec: CommandSpec) -> tuple[str, ...]:
    formats = [item for item in spec.formats if "?" not in item.split(" ", 1)[0]]
    if not formats or " " not in formats[0]:
        return ()
    arguments = formats[0].split(" ", 1)[1]
    return tuple(re.sub(r"\s+", "", name).lower() for name in _PLACEHOLDER.findall(arguments))


def _matches_scpi_enum(value: str, option: str) -> bool:
    if any(char in option for char in "<[]> ,"):
        return False
    value = value.strip().upper()
    full = option.upper()
    required = "".join(char for char in option if not char.isalpha() or char.isupper()).upper()
    if full.replace(".", "", 1).isdigit():
        return value == full
    return len(value) >= len(required) and full.startswith(value)


def validate_set_values(spec: CommandSpec, values: list[str]) -> None:
    """Validate simple one-argument enums; leave conditional/prose forms to hardware.

    This intentionally validates only cases the guide describes unambiguously.  It
    never guesses numeric ranges from model-dependent prose.
    """
    names = write_argument_names(spec)
    enums = declared_enums(spec)
    if len(names) != 1 or len(values) != 1 or names[0] not in enums:
        return
    options = enums[names[0]]
    if not options or any(any(char in option for char in "<[]> ,") for option in options):
        return
    if not any(_matches_scpi_enum(values[0], option) for option in options):
        raise ProtocolError(
            f"{spec.name} value {values[0]!r} is not declared by the guide; expected "
            + "|".join(options)
        )

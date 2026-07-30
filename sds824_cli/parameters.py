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
    """Validate clear manual constraints plus connected SDS824 restrictions."""
    names = write_argument_names(spec)
    enums = declared_enums(spec)
    unsupported = SDS824_UNSUPPORTED_ENUMS.get(spec.name, set())
    requested = values[0].strip().upper() if len(values) == 1 else ""
    declared_options = enums.get(names[0], ()) if len(names) == 1 else ()
    blocked = requested in unsupported or any(
        option.upper() in unsupported and _matches_scpi_enum(requested, option)
        for option in declared_options
    )
    if blocked:
        raise ProtocolError(
            f"{spec.name} value {values[0]!r} is documented for the series but rejected by the tested SDS824"
        )
    if spec.name in SDS824_NUMERIC_RANGES and len(values) == 1:
        low, high = SDS824_NUMERIC_RANGES[spec.name]
        try:
            numeric = float(values[0])
        except ValueError:
            pass
        else:
            if not low <= numeric <= high:
                raise ProtocolError(f"{spec.name} requires {low:g}..{high:g} on the tested SDS824")
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

SDS824_UNSUPPORTED_ENUMS: dict[str, set[str]] = {
    "channel.n.bwlimit": {"200M"},
    "channel.n.impedance": {"FIFTY"},
    "decode.bus.n.spi.dlength": {"64", "96"},
    "measure.advanced.statistics.histogram": {"ON"},
    "function.x.invert": {"ON"},
    "system.menu": {"OFF"},
    "trigger.video.fcnt": {"2", "4", "8"},
}

for _name in (
    "trigger.edge.holdoff", "trigger.slope.holdoff", "trigger.pulse.holdoff",
    "trigger.window.holdoff", "trigger.interval.holdoff", "trigger.dropout.holdoff",
    "trigger.runt.holdoff", "trigger.pattern.holdoff", "trigger.nedge.holdoff",
):
    SDS824_UNSUPPORTED_ENUMS[_name] = {"EVENTS"}

SDS824_NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "display.transparence": (20.0, 80.0),
}


def values_equivalent(request: str, response: str) -> bool:
    request = request.strip().upper()
    response = response.strip().upper()
    # The programming guide spells the trigger serial least-significant-bit
    # token "LSM", while this firmware consistently reports the canonical LSB.
    if (request, response) == ("LSM", "LSB"):
        return True
    if request == response:
        return True
    try:
        left, right = float(request), float(response)
        return abs(left - right) <= max(1e-15, abs(left) * 1e-9, abs(right) * 1e-9)
    except ValueError:
        return response.startswith(request) or request.startswith(response)


def can_verify_set(spec: CommandSpec, values: list[str]) -> bool:
    names = write_argument_names(spec)
    return (
        spec.can_query
        and spec.name not in {"wgen.output", "wgen.arbwave"}
        and 0 < len(values) <= len(names)
    )


def set_values_equivalent(
    requests: list[str], response: str, spec: CommandSpec | None = None,
) -> bool:
    requested = [
        part.strip()
        for request in requests
        for part in request.split(",")
    ]
    responses = [part.strip() for part in response.split(",")]
    # PROBe writes use "VALue,<factor>" or "DEFault", but PROBe? returns only
    # the effective numeric attenuation. Compare the factor rather than the
    # write-mode selector.
    if spec is not None and spec.name == "channel.n.probe":
        if requested and _matches_scpi_enum(requested[0], "VALue"):
            return (
                len(requested) == 2
                and len(responses) == 1
                and values_equivalent(requested[1], responses[0])
            )
        if requested and _matches_scpi_enum(requested[0], "DEFault"):
            return len(responses) == 1 and values_equivalent("1", responses[0])
    return len(requested) <= len(responses) and all(
        values_equivalent(request, returned)
        for request, returned in zip(requested, responses)
    )

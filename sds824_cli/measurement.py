"""Aggregated, triggered, and auto-ranged SDS824 measurements."""

from __future__ import annotations

import math
import random
import re
import statistics
import sys
import time
from contextlib import suppress

from .errors import ProtocolError, Sds824Error
from .parameters import set_values_equivalent
from .transport import LinuxUsbtmc

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


def _measure(
    scope: LinuxUsbtmc,
    metrics: list[str],
    source: str,
    *,
    autorange: bool = True,
    voltage_autorange: bool | None = None,
    time_autorange: bool | None = None,
    auto_trigger: bool = True,
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
        trigger_confirmed = False
        for _attempt in range(6):
            time.sleep(random.uniform(0.04, 0.08))
            try:
                trigger_status = scope.query_text(":TRIGger:STATus?").strip().lower()
            except Sds824Error:
                trigger_status = "unknown"
            if trigger_status in {"trig'd", "triggered", "stop"}:
                trigger_confirmed = True
                break
        final = sample_groups(count=5, random_intervals=True)
        unstable: list[str] = []
        unstable_names: set[str] = set()
        pkpk_reference = abs(float(final.get("PKPK", 0.0))) if isinstance(final.get("PKPK"), float) else 0.0
        for name in names:
            numeric: list[float] = []
            for group in last_groups:
                with suppress(ValueError):
                    numeric.append(float(group[name]))
            if len(numeric) != len(last_groups):
                unstable.append(name.lower() + "=intermittent")
                unstable_names.add(name)
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
                unstable_names.add(name)
        if unstable:
            print("warning: unstable " + " ".join(unstable), file=sys.stderr)
        timing_names = {
            "PER", "FREQ", "PWID", "NWID", "DUTY", "NDUTY", "WID",
            "NBWID", "DELAY", "TIMEL", "RISE", "FALL", "CCJ",
        }
        requested_timing = [name for name in names if name in timing_names]
        timing_valid = bool(requested_timing) and all(
            isinstance(final.get(name), float) and name not in unstable_names
            for name in requested_timing
        )
        if requested_timing and not trigger_confirmed and not timing_valid:
            print("warning: trigger unconfirmed", file=sys.stderr)
        return final

    def next_scale(value: float) -> float:
        value = min(10.0, max(5e-4, value))
        decade = 10.0 ** math.floor(math.log10(value))
        for step in (1.0, 2.0, 5.0, 10.0):
            candidate = step * decade
            if candidate >= value * (1.0 - 1e-12):
                return min(10.0, max(5e-4, candidate))
        raise AssertionError("unreachable")

    def time_steps() -> list[float]:
        return [multiplier * 10.0**exponent for exponent in range(-10, 4) for multiplier in (1, 2, 5)]

    def shifted_time_scale(value: float, offset: int) -> float:
        steps = time_steps()
        index = min(range(len(steps)), key=lambda item: abs(math.log(steps[item] / value)))
        return steps[min(len(steps) - 1, max(0, index + offset))]

    def nearest_time_scale(value: float) -> float:
        steps = time_steps()
        return min(steps, key=lambda item: abs(math.log(item / value)))

    def measured_period(values: dict[str, str | float]) -> float | None:
        period = values.get("PER")
        if isinstance(period, float) and period > 0:
            return period
        frequency = values.get("FREQ")
        if isinstance(frequency, float) and frequency > 0:
            return 1.0 / frequency
        return None

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
            if time_autorange and timing:
                try:
                    original_time_scale = float(scope.query_text(":TIMebase:SCALe?"))
                except ValueError:
                    original_time_scale = 0.0
                period = measured_period(result)
                if period is None and original_time_scale > 0:
                    # Search around the current setting rather than assuming
                    # that the signal is always slower than the display.
                    for offset in (1, -1, 2, -2, 3, -3):
                        candidate = shifted_time_scale(original_time_scale, offset)
                        scope.write(f":TIMebase:SCALe {candidate:.12g}")
                        time.sleep(0.3)
                        result = sample_groups()
                        period = measured_period(result)
                        if period is not None:
                            break
                if period is not None:
                    current_scale = float(scope.query_text(":TIMebase:SCALe?"))
                    displayed_cycles = 10.0 * current_scale / period
                    # A broad 2.5-6 cycle band prevents repeated 1-2-5
                    # switching while keeping roughly four periods visible.
                    if not 2.5 <= displayed_cycles <= 6.0:
                        target = nearest_time_scale(period * 0.4)
                        if not math.isclose(target, current_scale, rel_tol=1e-9):
                            scope.write(f":TIMebase:SCALe {target:.12g}")
                            time.sleep(0.3)
                            result = sample_groups()
            result = trigger_and_sample(result) if auto_trigger else sample_groups(
                count=5, random_intervals=True
            )
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
    requested = {
        "vertical_scale": args.vertical_scale,
        "time_scale": args.time_scale,
        "coupling": args.coupling,
    }
    if not any(value is not None for value in requested.values()):
        return {}
    source = args.source.upper()
    match = re.fullmatch(r"C([1-4])", source)
    if match is None:
        raise ProtocolError("measurement setup options require a physical C1..C4 source")
    channel = match.group(1)
    commands = [(f":CHANnel{channel}:SWITch", "ON")]
    if args.coupling:
        commands.append((f":CHANnel{channel}:COUPling", args.coupling))
    if args.vertical_scale:
        commands.append((f":CHANnel{channel}:SCALe", args.vertical_scale))
    if args.time_scale:
        commands.append((":TIMebase:SCALe", args.time_scale))
    result: dict[str, str] = {}
    for command, value in commands:
        scope.write(f"{command} {value}")
        actual = scope.query_text(command + "?")
        if not set_values_equivalent([value], actual):
            raise ProtocolError(
                f"measurement setup {command} requested {value!r}, readback is {actual!r}"
            )
        result[command] = actual
    return result

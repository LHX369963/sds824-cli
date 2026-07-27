import pytest

from sds824_cli.catalog import COMMANDS, get_command, render_command
from sds824_cli.errors import ProtocolError


def test_manual_catalog_is_complete_unique_and_sectioned():
    assert len(COMMANDS) == 705
    assert len({item.name for item in COMMANDS}) == 705
    assert {item.section for item in COMMANDS} == {
        "5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8",
        "5.9", "5.10", "5.11", "5.12", "5.13", "5.14", "5.15", "5.16",
        "5.17", "5.18", "5.19", "5.20", "5.21", "5.22", "5.23", "5.25",
    }


def test_known_query_set_and_action_kinds():
    assert get_command("ieee.idn").kind == "query"
    assert get_command("ieee.rst").kind == "action"
    assert get_command("channel.n.scale").kind == "query-set"
    assert get_command("waveform.source").kind == "query-set"


def test_render_all_five_manual_path_placeholders():
    cases = {
        "channel.n.scale": ({"n": 2}, ":CHANnel2:SCALe"),
        "root.function.x": ({"x": 1}, ":FUNCtion1"),
        "memory.m.horizontal.scale": ({"m": 1}, ":MEMory1:HORizontal:SCALe"),
        "ref.r.label": ({"r": "A"}, ":REFA:LABel"),
        "digital.d.d": ({"d": 0}, ":DIGital:D0"),
    }
    for name, (variables, expected) in cases.items():
        assert render_command(get_command(name), variables) == expected


def test_missing_or_unsafe_path_placeholder_is_rejected():
    spec = get_command("channel.n.scale")
    with pytest.raises(ProtocolError, match="requires --n"):
        render_command(spec, {})
    with pytest.raises(ProtocolError, match="invalid --n"):
        render_command(spec, {"n": "1;RST"})


def test_unknown_catalog_name_is_actionable():
    with pytest.raises(ProtocolError, match="commands list"):
        get_command("missing")

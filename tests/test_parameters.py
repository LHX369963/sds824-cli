import pytest

from sds824_cli.catalog import get_command
from sds824_cli.errors import ProtocolError
from sds824_cli.parameters import declared_enums, validate_set_values, write_argument_names


def test_extract_simple_enum_and_argument_name():
    spec = get_command("channel.n.coupling")
    assert write_argument_names(spec) == ("coupling_mode",)
    assert declared_enums(spec)["coupling_mode"] == ("AC", "DC", "GND")


def test_simple_enum_accepts_scpi_long_and_abbreviated_spellings():
    spec = get_command("trigger.edge.slope")
    validate_set_values(spec, ["RISING"])
    validate_set_values(spec, ["RIS"])
    with pytest.raises(ProtocolError, match="not declared"):
        validate_set_values(spec, ["BOTH"])


def test_conditional_and_multi_argument_forms_remain_available():
    validate_set_values(get_command("acquire.type"), ["AVERage,16"])
    validate_set_values(get_command("channel.n.probe"), ["VALue", "10"])

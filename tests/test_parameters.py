import pytest

from sds824_cli.catalog import get_command
from sds824_cli.errors import ProtocolError
from sds824_cli.parameters import (
    can_verify_set,
    declared_enums,
    set_values_equivalent,
    validate_set_values,
    write_argument_names,
)


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


def test_connected_sds824_restrictions_are_rejected_before_io():
    with pytest.raises(ProtocolError, match="rejected by the tested SDS824"):
        validate_set_values(get_command("channel.n.bwlimit"), ["200M"])
    with pytest.raises(ProtocolError, match="rejected by the tested SDS824"):
        validate_set_values(get_command("channel.n.impedance"), ["FIFT"])
    with pytest.raises(ProtocolError, match="20..80"):
        validate_set_values(get_command("display.transparence"), ["0"])
    with pytest.raises(ProtocolError, match="rejected by the tested SDS824"):
        validate_set_values(get_command("decode.bus.n.spi.dlength"), ["64"])


def test_firmware_serial_bit_order_alias_is_equivalent():
    from sds824_cli.parameters import values_equivalent

    assert values_equivalent("LSM", "LSB")


def test_multi_argument_readback_verification():
    spec = get_command("format.data")
    assert can_verify_set(spec, ["CUSTom", "3"])
    assert set_values_equivalent(["CUSTom", "3"], "CUSTOM,3")
    assert set_values_equivalent(["CUSTom"], "CUSTOM,14")
    assert set_values_equivalent(["AVERage,16"], "AVERAGE,16")
    assert not set_values_equivalent(["CUSTom", "3"], "CUSTOM,14")

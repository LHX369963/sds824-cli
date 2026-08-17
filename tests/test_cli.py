from contextlib import contextmanager
from types import SimpleNamespace
import struct

import pytest

import sds824_cli.cli as cli
from sds824_cli.errors import TransportError


@pytest.fixture(autouse=True)
def no_cli_sleep(monkeypatch):
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)


class FakeScope:
    def __init__(self):
        self.writes = []
        self.queries = []
        self.query_kwargs = []

    def write(self, command, **kwargs):
        self.writes.append(command)

    def query(self, command, **kwargs):
        self.queries.append(command)
        self.query_kwargs.append(kwargs)
        return b"1.00E+00\n"

    def query_text(self, command, **kwargs):
        self.queries.append(command)
        return "1.00E+00"


@contextmanager
def fake_session(scope):
    yield scope


def test_normal_sessions_do_not_clear_on_open():
    parser = cli._build_parser()
    assert parser.parse_args(["info"]).clear_on_open is False
    assert parser.parse_args(["--clear-on-open", "info"]).clear_on_open is True
    assert parser.parse_args(["--no-clear", "info"]).clear_on_open is False


def test_catalog_get_set_and_path_render(monkeypatch, capsys):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["set", "channel.n.scale", "0.5", "--n", "2", "--no-verify"]) == 0
    assert scope.writes == [":CHANnel2:SCALe 0.5"]
    assert cli.main(["get", "channel.n.scale", "--n", "2"]) == 0
    assert scope.queries[-1] == ":CHANnel2:SCALe?"
    assert capsys.readouterr().out.strip() == "1.00E+00"


def test_multi_argument_commands_preserve_manual_commas(monkeypatch, capsys):
    class MultiScope(FakeScope):
        def query_text(self, command, **kwargs):
            self.queries.append(command)
            return "CUSTOM,3"

    scope = MultiScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["set", "format.data", "CUSTom", "3"]) == 0
    assert scope.writes == [":FORMat:DATA CUSTom,3"]
    assert scope.queries == [":FORMat:DATA?"]

    assert cli.main(["action", "measure.simple.item", "FREQ", "ON"]) == 0
    assert scope.writes[-1] == ":MEASure:SIMPle:ITEM FREQ,ON"

    assert cli.main(["get", "root.print", "PNG", "NORMal"]) == 0
    assert scope.queries[-1] == ":PRINt? PNG,NORMal"
    assert capsys.readouterr().out.strip() == "1.00E+00"


def test_wgen_output_preserves_required_scpi_literals(monkeypatch):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main([
        "set", "wgen.output", "ON", "50", "NOR", "--channel", "C1",
        "--allow-unsupported", "--no-verify",
    ]) == 0
    assert scope.writes == ["C1:OUTPut ON,LOAD,50,PLRTNOR"]


def test_destructive_action_requires_confirmation(capsys):
    assert cli.main(["action", "ieee.rst"]) == 1
    assert "repeat with --yes" in capsys.readouterr().err


def test_commands_audit_reports_all_manual_blocks(capsys):
    assert cli.main(["commands", "audit"]) == 0
    assert '"manual_command_blocks": 712' in capsys.readouterr().out


def test_commands_show_is_concise_by_default(capsys):
    assert cli.main(["commands", "show", "channel.n.scale"]) == 0
    assert capsys.readouterr().out == "channel.n.scale  :CHANnel<n>:SCALe <scale>  query,set\n"


def test_commands_show_verbose_preserves_full_metadata(capsys):
    assert cli.main(["commands", "show", "channel.n.scale", "--verbose", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["description"]
    assert payload["pdf_page"] == 56


def test_negative_scientific_set_value_reaches_transport(monkeypatch):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["set", "channel.n.skew", "-1e-7", "--n", "1", "--no-verify"]) == 0
    assert scope.writes == [":CHANnel1:SKEW -1e-7"]


def test_other_model_and_optional_paths_require_explicit_override(capsys):
    assert cli.main(["action", "meter.mmeter", "ON"]) == 1
    assert "other-model" in capsys.readouterr().err
    assert cli.main(["get", "wgen.output", "--channel", "C1"]) == 1
    assert "optional" in capsys.readouterr().err


def test_set_readback_rejects_ignored_value(monkeypatch, capsys):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["set", "display.transparence", "50"]) == 1
    assert "readback is '1.00E+00'" in capsys.readouterr().err


def test_set_readback_accepts_equivalent_unit_and_scientific_notation(monkeypatch):
    class NormalizingScope(FakeScope):
        def query_text(self, command, **kwargs):
            self.queries.append(command)
            return "1.00E-01"

    scope = NormalizingScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["set", "channel.n.scale", "0.1V", "--n", "1"]) == 0
    assert scope.writes == [":CHANnel1:SCALe 0.1V"]


def test_known_timeout_measurement_is_rejected_before_io(monkeypatch, capsys):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["measure", "rise20t80"]) == 1
    assert "times out on the tested SDS824" in capsys.readouterr().err
    assert not scope.writes and not scope.queries


def test_unknown_measurement_is_concise(monkeypatch, capsys):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["measure", "not-a-metric"]) == 1
    assert capsys.readouterr().err == "error: unknown measurement 'not-a-metric'\n"
    assert not scope.writes and not scope.queries


def test_measure_all_uses_one_temporary_item_and_accepts_c4(monkeypatch, capsys):
    class MeasureScope(FakeScope):
        def query_text(self, command, **kwargs):
            self.queries.append(command)
            if command == ":MEASure?":
                return "OFF"
            if command == ":MEASure:SIMPle:SOURce?":
                return "C2"
            if command.startswith(":MEASure:SIMPle:VALue?") and not any(
                write.endswith(",ON") for write in self.writes
            ):
                return "The number of measurements is zero"
            return "1.00E+00"

    scope = MeasureScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["measure", "all", "--source", "C4", "--json"]) == 0
    item_writes = [write for write in scope.writes if ":MEASure:SIMPle:ITEM" in write]
    assert item_writes == [
        ":MEASure:SIMPle:ITEM PKPK,ON",
        ":MEASure:SIMPle:ITEM PKPK,OFF",
    ]
    assert ":MEASure:SIMPle:SOURce C2" in scope.writes
    assert ":MEASure OFF" in scope.writes
    assert '"source":"C4"' in capsys.readouterr().out


def test_measure_multiple_filters_unavailable_and_prints_compact_json(monkeypatch, capsys):
    class MeasureScope(FakeScope):
        def query_text(self, command, **kwargs):
            if command == ":MEASure?":
                return "ON"
            if command == ":MEASure:SIMPle:SOURce?":
                return "C1"
            if command.endswith("FREQ"):
                return "****"
            return "1.25"

    monkeypatch.setattr(cli, "_session", lambda args: fake_session(MeasureScope()))
    assert cli.main(["measure", "pkpk", "mean", "freq", "--json"]) == 0
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    assert '"pkpk":1.25' in output and '"mean":1.25' in output
    assert '"freq"' not in output
    assert '"unavailable":1' in output


def test_measure_uses_internal_three_group_median(monkeypatch):
    class MeasureScope(FakeScope):
        values = iter(("1", "1", "100", "2"))  # availability probe, then 3 groups

        def query_text(self, command, **kwargs):
            if command == ":MEASure?":
                return "ON"
            if command == ":MEASure:SIMPle:SOURce?":
                return "C1"
            if command == ":MEASure:SIMPle:VALue? FREQ":
                return next(self.values)
            return "1"

    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert cli._measure(MeasureScope(), ["freq"], "C1", autorange=False) == {"freq": 2.0}


def test_measure_autorange_moves_directly_and_stops_in_hysteresis_band(monkeypatch):
    class MeasureScope(FakeScope):
        scale = 0.2
        offset = 0.0

        def write(self, command, **kwargs):
            super().write(command, **kwargs)
            if command.startswith(":CHANnel1:SCALe "):
                self.scale = float(command.rsplit(" ", 1)[1])
            if command.startswith(":CHANnel1:OFFSet "):
                self.offset = float(command.rsplit(" ", 1)[1])

        def query_text(self, command, **kwargs):
            if command == ":MEASure?":
                return "ON"
            if command == ":MEASure:SIMPle:SOURce?":
                return "C1"
            if command == ":CHANnel1:SCALe?":
                return str(self.scale)
            if command == ":CHANnel1:OFFSet?":
                return str(self.offset)
            expanded = self.scale >= 0.5
            values = {
                "FREQ": "2000",
                "PKPK": "1.5" if expanded else "1.4",
                "MAX": "0.95" if expanded else "0.8",
                "MIN": "-0.55" if expanded else "-0.6",
                "MEAN": "0.2" if expanded else "0.1",
            }
            if command.startswith(":MEASure:SIMPle:VALue? "):
                return values[command.rsplit(" ", 1)[1]]
            return "1"

    scope = MeasureScope()
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert cli._measure(scope, ["freq", "pkpk"], "C1") == {
        "freq": 2000.0,
        "pkpk": 1.5,
    }
    assert [w for w in scope.writes if w.startswith(":CHANnel1:SCALe ")] == [
        ":CHANnel1:SCALe 0.5"
    ]
    assert ":TRIGger:EDGE:SOURce C1" in scope.writes
    assert ":TRIGger:RUN" in scope.writes


def test_measure_warns_on_random_interval_instability(capsys):
    class DynamicScope(FakeScope):
        triggered = False
        freq_values = iter((1000, 1200, 800, 1250, 900))

        def write(self, command, **kwargs):
            super().write(command, **kwargs)
            if command == ":TRIGger:RUN":
                self.triggered = True

        def query_text(self, command, **kwargs):
            if command == ":MEASure?":
                return "ON"
            if command == ":MEASure:SIMPle:SOURce?":
                return "C1"
            if command == ":CHANnel1:SCALe?":
                return "0.2"
            if command == ":CHANnel1:OFFSet?":
                return "0"
            if command == ":TRIGger:STATus?":
                return "Trig'd"
            values = {"PKPK": "1", "MAX": "0.5", "MIN": "-0.5", "MEAN": "0"}
            if command == ":MEASure:SIMPle:VALue? FREQ":
                return str(next(self.freq_values)) if self.triggered else "1000"
            if command.startswith(":MEASure:SIMPle:VALue? "):
                return values[command.rsplit(" ", 1)[1]]
            return "1"

    cli._measure(DynamicScope(), ["freq"], "C1")
    assert capsys.readouterr().err == "warning: unstable freq=800..1250\n"


def test_measure_warns_but_continues_when_trigger_fails(capsys):
    class UntriggeredScope(FakeScope):
        def query_text(self, command, **kwargs):
            if command == ":MEASure?":
                return "ON"
            if command == ":MEASure:SIMPle:SOURce?":
                return "C1"
            if command == ":CHANnel1:SCALe?":
                return "0.2"
            if command == ":CHANnel1:OFFSet?":
                return "0"
            if command == ":TRIGger:STATus?":
                return "Auto"
            values = {"FREQ": "1000", "PKPK": "1", "MAX": "0.5", "MIN": "-0.5", "MEAN": "0"}
            if command.startswith(":MEASure:SIMPle:VALue? "):
                return values[command.rsplit(" ", 1)[1]]
            return "1"

    assert cli._measure(UntriggeredScope(), ["freq"], "C1") == {"freq": 1000.0}
    assert capsys.readouterr().err == "warning: trigger Auto\n"


def test_measure_setup_uses_same_session_and_verifies_readback(monkeypatch, capsys):
    class MeasureScope(FakeScope):
        def query_text(self, command, **kwargs):
            self.queries.append(command)
            return {
                ":CHANnel1:SWITch?": "ON",
                ":CHANnel1:COUPling?": "DC",
                ":CHANnel1:SCALe?": "2.00E-01",
                ":CHANnel1:OFFSet?": "0",
                ":TIMebase:SCALe?": "2.00E-04",
                ":TRIGger:STATus?": "Trig'd",
                ":MEASure?": "ON",
                ":MEASure:SIMPle:SOURce?": "C1",
                ":MEASure:SIMPle:VALue? FREQ": "1000.0",
                ":MEASure:SIMPle:VALue? PKPK": "1.02",
                ":MEASure:SIMPle:VALue? MAX": "0.51",
                ":MEASure:SIMPle:VALue? MIN": "-0.51",
                ":MEASure:SIMPle:VALue? MEAN": "0",
            }[command]

    scope = MeasureScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main([
        "measure", "freq", "pkpk", "--source", "C1", "--vertical-scale", "200mV",
        "--time-scale", "200us", "--coupling", "DC", "--json",
    ]) == 0
    output = capsys.readouterr().out
    assert '"freq":1000.0' in output and '"pkpk":1.02' in output
    assert '"setup"' in output
    assert [write for write in scope.writes if write.startswith(":CHANnel1:SCALe ")] == [
        ":CHANnel1:SCALe 200mV"
    ]
    assert [write for write in scope.writes if write.startswith(":TIMebase:SCALe ")] == [
        ":TIMebase:SCALe 200us"
    ]


def test_measure_setup_rejects_math_source_before_writes(monkeypatch, capsys):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["measure", "freq", "--source", "M1", "--time-scale", "1ms"]) == 1
    assert "physical C1..C4" in capsys.readouterr().err
    assert not scope.writes


def test_measure_expectations_choose_125_setup(monkeypatch, capsys):
    class MeasureScope(FakeScope):
        def query_text(self, command, **kwargs):
            self.queries.append(command)
            return {
                ":CHANnel1:SWITch?": "ON",
                ":CHANnel1:COUPling?": "DC",
                ":CHANnel1:SCALe?": "5.00E-01",
                ":CHANnel1:OFFSet?": "-2.00E-01",
                ":TIMebase:SCALe?": "1.00E-04",
                ":TRIGger:STATus?": "Trig'd",
                ":MEASure?": "ON",
                ":MEASure:SIMPle:SOURce?": "C1",
                ":MEASure:SIMPle:VALue? FREQ": "2000",
                ":MEASure:SIMPle:VALue? PKPK": "1.5",
                ":MEASure:SIMPle:VALue? MAX": "0.95",
                ":MEASure:SIMPle:VALue? MIN": "-0.55",
                ":MEASure:SIMPle:VALue? MEAN": "0.2",
            }[command]

    scope = MeasureScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert cli.main([
        "measure", "freq", "--source", "C1", "--expect-frequency", "2kHz",
        "--expect-pkpk", "1.5Vpp", "--expect-offset", "0.2V",
    ]) == 0
    assert ":CHANnel1:SCALe 0.5V" in scope.writes
    assert ":CHANnel1:COUPling DC" in scope.writes
    assert ":CHANnel1:OFFSet -0.2V" in scope.writes
    assert ":TIMebase:SCALe 0.0001S" in scope.writes
    assert capsys.readouterr().out == "2000.0\n"


def test_info_rejects_empty_identity(monkeypatch, capsys):
    class EmptyScope(FakeScope):
        def query_text(self, command, **kwargs):
            return ""

    monkeypatch.setattr(cli, "_session", lambda args: fake_session(EmptyScope()))
    assert cli.main(["info"]) == 1
    assert "invalid or empty *IDN?" in capsys.readouterr().err


def test_screenshot_uses_retry_options(monkeypatch, tmp_path):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    output = tmp_path / "screen.png"
    assert cli.main(["screenshot", str(output), "--retries", "2", "--retry-delay", "0.75"]) == 0
    assert scope.query_kwargs[-1] == {"retries": 2, "retry_delay_ms": 750.0}


def test_waveform_reads_data_before_preamble_to_preserve_deep_memory():
    descriptor = bytearray(346)
    descriptor[:8] = b"WAVEDESC"
    struct.pack_into("<h", descriptor, 32, 1)
    struct.pack_into("<h", descriptor, 34, 0)
    struct.pack_into("<i", descriptor, 36, 346)
    struct.pack_into("<i", descriptor, 60, 4)
    struct.pack_into("<i", descriptor, 116, 2)
    struct.pack_into("<f", descriptor, 164, 7680.0)
    struct.pack_into("<h", descriptor, 172, 12)
    struct.pack_into("<f", descriptor, 176, 1e-9)
    struct.pack_into("<f", descriptor, 328, 1.0)

    def block(payload):
        length = str(len(payload)).encode()
        return b"#" + str(len(length)).encode() + length + payload

    class WaveScope(FakeScope):
        def query_text(self, command, **kwargs):
            self.queries.append(command)
            return {
                ":WAVeform:SOURce?": "C1",
                ":WAVeform:WIDTh?": "WORD",
                ":WAVeform:BYTeorder?": "LSB",
                ":WAVeform:STARt?": "0",
                ":WAVeform:INTerval?": "1",
                ":WAVeform:POINt?": "0",
                ":TRIGger:STATus?": "STOP",
            }[command]

        def query(self, command, **kwargs):
            self.queries.append(command)
            if command == ":WAVeform:DATA?":
                return block(struct.pack("<hh", 16, -16))
            if command == ":WAVeform:PREamble?":
                return block(bytes(descriptor))
            raise AssertionError(command)

    scope = WaveScope()
    args = SimpleNamespace(
        stop=False, source="C2", width="WORD", start=0, interval=1, points=2
    )
    wave = cli._capture_waveform(scope, args)
    assert wave.codes() == [16, -16]
    assert scope.queries.index(":WAVeform:DATA?") < scope.queries.index(":WAVeform:PREamble?")


def test_waveform_accepts_instrument_adjusted_point_count():
    descriptor = bytearray(346)
    descriptor[:8] = b"WAVEDESC"
    struct.pack_into("<h", descriptor, 32, 1)
    struct.pack_into("<h", descriptor, 34, 0)
    struct.pack_into("<i", descriptor, 36, 346)
    struct.pack_into("<i", descriptor, 60, 4)
    struct.pack_into("<i", descriptor, 116, 2)
    struct.pack_into("<f", descriptor, 164, 7680.0)
    struct.pack_into("<h", descriptor, 172, 12)
    struct.pack_into("<f", descriptor, 176, 1e-9)
    struct.pack_into("<f", descriptor, 328, 1.0)

    def block(payload):
        length = str(len(payload)).encode()
        return b"#" + str(len(length)).encode() + length + payload

    class WaveScope(FakeScope):
        def query_text(self, command, **kwargs):
            self.queries.append(command)
            return {
                ":WAVeform:SOURce?": "C1",
                ":WAVeform:WIDTh?": "WORD",
                ":WAVeform:BYTeorder?": "LSB",
                ":WAVeform:STARt?": "0",
                ":WAVeform:INTerval?": "1",
                ":WAVeform:POINt?": "0",
                ":TRIGger:STATus?": "STOP",
            }[command]

        def query(self, command, **kwargs):
            self.queries.append(command)
            if command == ":WAVeform:DATA?":
                return block(struct.pack("<hh", 16, -16))
            if command == ":WAVeform:PREamble?":
                return block(bytes(descriptor))
            raise AssertionError(command)

    scope = WaveScope()
    args = SimpleNamespace(
        stop=False, source="C2", width="WORD", start=0, interval=1, points=100000
    )
    wave = cli._capture_waveform(scope, args)
    assert wave.point_count == 2


def test_waveform_omits_point_command_when_points_not_given():
    descriptor = bytearray(346)
    descriptor[:8] = b"WAVEDESC"
    struct.pack_into("<h", descriptor, 32, 1)
    struct.pack_into("<h", descriptor, 34, 0)
    struct.pack_into("<i", descriptor, 36, 346)
    struct.pack_into("<i", descriptor, 60, 4)
    struct.pack_into("<i", descriptor, 116, 2)
    struct.pack_into("<f", descriptor, 164, 7680.0)
    struct.pack_into("<h", descriptor, 172, 12)
    struct.pack_into("<f", descriptor, 176, 1e-9)
    struct.pack_into("<f", descriptor, 328, 1.0)

    def block(payload):
        length = str(len(payload)).encode()
        return b"#" + str(len(length)).encode() + length + payload

    class WaveScope(FakeScope):
        def query_text(self, command, **kwargs):
            self.queries.append(command)
            return {
                ":WAVeform:SOURce?": "C1",
                ":WAVeform:WIDTh?": "WORD",
                ":WAVeform:BYTeorder?": "LSB",
                ":WAVeform:STARt?": "0",
                ":WAVeform:INTerval?": "1",
                ":WAVeform:POINt?": "50000",
                ":TRIGger:STATus?": "STOP",
            }[command]

        def query(self, command, **kwargs):
            self.queries.append(command)
            if command == ":WAVeform:DATA?":
                return block(struct.pack("<hh", 16, -16))
            if command == ":WAVeform:PREamble?":
                return block(bytes(descriptor))
            raise AssertionError(command)

    scope = WaveScope()
    args = SimpleNamespace(
        stop=False, source="C2", width="WORD", start=0, interval=1, points=None
    )
    wave = cli._capture_waveform(scope, args)
    assert wave.point_count == 2
    assert [command for command in scope.writes if command.startswith(":WAVeform:POINt ")] == [
        ":WAVeform:POINt 50000"
    ]


def test_recover_reopens_after_failed_probe(monkeypatch, capsys):
    device = type("Device", (), {"serial": "SDS08TEST"})()

    class RecoverScope:
        probes = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def query_text(self, command):
            RecoverScope.probes += 1
            if RecoverScope.probes == 1:
                raise TransportError("injected timeout")
            return "Siglent Technologies,SDS824X HD,SDS08TEST,4.8"

    monkeypatch.setattr(cli, "choose_device", lambda *args, **kwargs: device)
    monkeypatch.setattr(cli, "LinuxUsbtmc", RecoverScope)
    assert cli.main(["recover", "--attempts", "2", "--delay", "0"]) == 0
    output = capsys.readouterr().out
    assert '"method": "usbtmc-clear"' in output
    assert '"failed_probes": 1' in output


def test_recover_escalates_to_usb_reset(monkeypatch, capsys):
    device = type("Device", (), {"serial": "SDS08TEST"})()
    reset_calls = []

    class RecoverScope:
        probes = 0
        reset_done = False

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def query_text(self, command):
            RecoverScope.probes += 1
            if not RecoverScope.reset_done:
                raise TransportError("injected persistent timeout")
            return "Siglent Technologies,SDS824X HD,SDS08TEST,4.8"

    def fake_reset(selected):
        reset_calls.append(selected)
        RecoverScope.reset_done = True
        return "/dev/bus/usb/001/002"

    monkeypatch.setattr(cli, "choose_device", lambda *args, **kwargs: device)
    monkeypatch.setattr(cli, "LinuxUsbtmc", RecoverScope)
    monkeypatch.setattr(cli, "reset_usb_device", fake_reset)
    assert cli.main(["recover", "--attempts", "2", "--delay", "0", "--usb-reset"]) == 0
    output = capsys.readouterr().out
    assert '"method": "usb-reset"' in output
    assert '"usb_node": "/dev/bus/usb/001/002"' in output
    assert reset_calls == [device]
import json

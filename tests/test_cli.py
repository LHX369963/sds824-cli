from contextlib import contextmanager

import sds824_cli.cli as cli
from sds824_cli.errors import TransportError


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


def test_catalog_get_set_and_path_render(monkeypatch, capsys):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["set", "channel.n.scale", "0.5", "--n", "2", "--no-verify"]) == 0
    assert scope.writes == [":CHANnel2:SCALe 0.5"]
    assert cli.main(["get", "channel.n.scale", "--n", "2"]) == 0
    assert scope.queries[-1] == ":CHANnel2:SCALe?"
    assert capsys.readouterr().out.strip() == "1.00E+00"


def test_destructive_action_requires_confirmation(capsys):
    assert cli.main(["action", "ieee.rst"]) == 1
    assert "repeat with --yes" in capsys.readouterr().err


def test_commands_audit_reports_all_manual_blocks(capsys):
    assert cli.main(["commands", "audit"]) == 0
    assert '"manual_command_blocks": 712' in capsys.readouterr().out


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


def test_known_timeout_measurement_is_rejected_before_io(monkeypatch, capsys):
    scope = FakeScope()
    monkeypatch.setattr(cli, "_session", lambda args: fake_session(scope))
    assert cli.main(["measure", "rise20t80"]) == 1
    assert "times out on the tested SDS824" in capsys.readouterr().err
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
    assert '"source": "C4"' in capsys.readouterr().out


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

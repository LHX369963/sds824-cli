from contextlib import contextmanager

import sds824_cli.cli as cli


class FakeScope:
    def __init__(self):
        self.writes = []
        self.queries = []

    def write(self, command, **kwargs):
        self.writes.append(command)

    def query(self, command, **kwargs):
        self.queries.append(command)
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

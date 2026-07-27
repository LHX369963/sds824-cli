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
    assert cli.main(["set", "channel.n.scale", "0.5", "--n", "2"]) == 0
    assert scope.writes == [":CHANnel2:SCALe 0.5"]
    assert cli.main(["get", "channel.n.scale", "--n", "2"]) == 0
    assert scope.queries[-1] == ":CHANnel2:SCALe?"
    assert capsys.readouterr().out.strip() == "1.00E+00"


def test_destructive_action_requires_confirmation(capsys):
    assert cli.main(["action", "ieee.rst"]) == 1
    assert "repeat with --yes" in capsys.readouterr().err


def test_commands_audit_reports_all_manual_blocks(capsys):
    assert cli.main(["commands", "audit"]) == 0
    assert '"manual_command_blocks": 705' in capsys.readouterr().out

from typer.testing import CliRunner

from infinite_buying_dbapi.cli import app
from infinite_buying_dbapi.store import StateStore


def test_cli_help_and_preview_workflow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IB_DB_PATH", str(tmp_path / "state.sqlite3"))
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["setup", "--account-alias", "test"]).exit_code == 0
    created = runner.invoke(app, ["profile", "create", "p1", "--symbol", "TQQQ", "--division", "40", "--capital", "10000", "--effective-from", "2026-01-02"])
    assert created.exit_code == 0, created.output
    assert StateStore(tmp_path / "state.sqlite3").get_profile("p1").account_alias == "test"
    preview = runner.invoke(app, ["preview", "p1", "--previous-close", "100", "--session-date", "2026-01-05"])
    assert preview.exit_code == 0, preview.output
    assert '"initial_buy"' in preview.output


def test_cli_rejects_invalid_decimal_and_date(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IB_DB_PATH", str(tmp_path / "state.sqlite3"))
    runner = CliRunner()
    bad_capital = runner.invoke(app, ["profile", "create", "p1", "--symbol", "TQQQ", "--division", "40", "--capital", "KRW"])
    assert bad_capital.exit_code != 0

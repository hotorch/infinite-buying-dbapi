from typer.testing import CliRunner

from infinite_buying_dbapi.cli import app
from infinite_buying_dbapi.config import Settings
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


def test_official_form_oauth_is_default(monkeypatch) -> None:
    monkeypatch.delenv("IB_DBSEC_OAUTH_STYLE", raising=False)
    assert Settings(_env_file=None).dbsec_oauth_style == "form"


def test_setup_imports_issued_json_environment_fields(tmp_path, monkeypatch) -> None:
    imported = {}
    monkeypatch.setenv("IB_DB_PATH", str(tmp_path / "state.sqlite3"))
    monkeypatch.setenv("DB_APPKEY", "key-value")
    monkeypatch.setenv("DB_APPSECRET", "secret-value")
    monkeypatch.setenv("DB_ENV", "real")
    monkeypatch.setenv("DB_EXPIRE_DATE", "20991231")
    monkeypatch.setattr("infinite_buying_dbapi.cli.store_secret", lambda alias, name, value: imported.__setitem__((alias, name), value))

    result = CliRunner().invoke(app, ["setup", "--account-alias", "test", "--import-env-credentials"])

    assert result.exit_code == 0, result.output
    assert imported == {("test", "app_key"): "key-value", ("test", "app_secret"): "secret-value"}
    assert "key-value" not in result.output and "secret-value" not in result.output


def test_dbsec_cli_output_is_minimal_and_never_calls_order_path(tmp_path, monkeypatch) -> None:
    class ReadOnlyBroker:
        def holdings(self):
            return [{"SymCode": "TQQQ", "AstkExecBaseQty": "3", "account_number": "1234567890", "access_token": "token-value"}]

    store = StateStore(tmp_path / "state.sqlite3")
    monkeypatch.setattr("infinite_buying_dbapi.cli._read_only_broker", lambda: (ReadOnlyBroker(), store, "default"))
    result = CliRunner().invoke(app, ["dbsec", "holdings"])

    assert result.exit_code == 0, result.output
    assert "TQQQ\t3" in result.output
    assert "1234567890" not in result.output
    assert "token-value" not in result.output


def test_dbsec_cli_uses_symbol_market_code(tmp_path, monkeypatch) -> None:
    calls = []

    class ReadOnlyBroker:
        def current_price(self, symbol, market_code="FN"):
            calls.append((symbol, market_code))
            return "10.25"

    store = StateStore(tmp_path / "state.sqlite3")
    monkeypatch.setattr("infinite_buying_dbapi.cli._read_only_broker", lambda: (ReadOnlyBroker(), store, "default"))

    result = CliRunner().invoke(app, ["dbsec", "current-price", "--symbol", "SOXL"])

    assert result.exit_code == 0, result.output
    assert calls == [("SOXL", "FA")]
    assert "SOXL\t10.25" in result.output


def test_dbsec_auth_status_does_not_issue_token_or_print_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IB_DB_PATH", str(tmp_path / "state.sqlite3"))
    values = {"app_key": "key-value", "app_secret": "secret-value", "access_token_expires_at": "2099-12-31T00:00:00+00:00"}
    monkeypatch.setattr("infinite_buying_dbapi.cli.get_secret", lambda alias, name: values.get(name))

    result = CliRunner().invoke(app, ["dbsec", "auth-status"])

    assert result.exit_code == 0, result.output
    assert '"credentials_present":true' in result.output
    assert '"cached_token_valid":true' in result.output
    assert "key-value" not in result.output and "secret-value" not in result.output

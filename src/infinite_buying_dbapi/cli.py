from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from getpass import getpass
from pathlib import Path

import typer

from .api import envelope_json
from .auth import DbSecTokenManager, OAuthError
from .broker import AmbiguousOrderError, BrokerError, DbSecBroker
from .capital import CapitalError, apply_allocation, available_settled_usd
from .config import Settings
from .execution import ExecutionLimits, execute_intents
from .market_calendar import NEW_YORK, session_schedule
from .market_data import MARKET_CODES, collect_market_data, latest_completed_session
from .models import Environment, Phase, Side, StrategyProfile, canonical_json
from .positions import snapshot_cycle_session
from .rate_limit import DbSecRateLimiter
from .reconciliation import reconcile_dbsec
from .replay import replay_file
from .security import get_secret, redact, store_secret
from .service import plan_phase, preview_phase
from .store import StateStore
from .weather import SIGNAL_SYMBOLS, WeatherDataError, candles_from_rows, compute_weather_history

app = typer.Typer(no_args_is_help=True, help="Pure V4 + DB Securities operator CLI")
profile_app = typer.Typer(no_args_is_help=True)
capability_app = typer.Typer(no_args_is_help=True)
run_app = typer.Typer(no_args_is_help=True)
orders_app = typer.Typer(no_args_is_help=True)
emergency_app = typer.Typer(no_args_is_help=True)
backup_app = typer.Typer(no_args_is_help=True)
dbsec_app = typer.Typer(no_args_is_help=True, help="Read-only DB Securities account and market inquiries")
automation_app = typer.Typer(no_args_is_help=True)
capital_app = typer.Typer(no_args_is_help=True)
weather_app = typer.Typer(no_args_is_help=True)
position_app = typer.Typer(no_args_is_help=True)
report_app = typer.Typer(no_args_is_help=True)
dashboard_app = typer.Typer(no_args_is_help=True)
app.add_typer(profile_app, name="profile")
app.add_typer(capability_app, name="capability")
app.add_typer(run_app, name="run")
app.add_typer(orders_app, name="orders")
app.add_typer(emergency_app, name="emergency-stop")
app.add_typer(backup_app, name="backup")
app.add_typer(dbsec_app, name="dbsec")
app.add_typer(automation_app, name="automation")
app.add_typer(capital_app, name="capital")
app.add_typer(weather_app, name="weather")
app.add_typer(position_app, name="position")
app.add_typer(report_app, name="report")
app.add_typer(dashboard_app, name="dashboard")


def _context() -> tuple[Settings, StateStore]:
    settings = Settings()
    return settings, StateStore(settings.db_path)


def _live_broker(settings: Settings, store: StateStore, account_alias: str) -> DbSecBroker:
    if settings.dbsec_requests_per_second is None or settings.dbsec_requests_per_second <= 0:
        raise typer.BadParameter("IB_DBSEC_REQUESTS_PER_SECOND must be set from official per-TR rate evidence")
    token = DbSecTokenManager(
        settings.dbsec_base_url,
        account_alias,
        store,
        settings.request_timeout_seconds,
        oauth_style=settings.dbsec_oauth_style,
    ).access_token()
    limiter = DbSecRateLimiter(store, account_alias, settings.dbsec_requests_per_second)
    return DbSecBroker(settings.dbsec_base_url, token, settings.request_timeout_seconds, before_request=limiter.wait, account_alias=account_alias)


def _account_alias(settings: Settings, store: StateStore) -> str:
    return store.setting("account_alias", settings.account_alias) or settings.account_alias


def _read_only_broker() -> tuple[DbSecBroker, StateStore, str]:
    settings, store = _context()
    alias = _account_alias(settings, store)
    try:
        token = DbSecTokenManager(
            settings.dbsec_base_url,
            alias,
            store,
            settings.request_timeout_seconds,
            oauth_style=settings.dbsec_oauth_style,
        ).access_token()
        requests_per_second = settings.dbsec_requests_per_second or 1.0
        limiter = DbSecRateLimiter(store, alias, requests_per_second)
        broker = DbSecBroker(settings.dbsec_base_url, token, settings.request_timeout_seconds, before_request=limiter.wait, account_alias=alias)
        return broker, store, alias
    except (OAuthError, BrokerError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


def _symbol(row: dict[str, object]) -> str:
    return str(row.get("SymCode") or row.get("AstkIsuNo") or "-").split(".")[0].upper()


def _quantity(row: dict[str, object]) -> str:
    return str(row.get("AstkExecBaseQty") or row.get("AstkBalQty") or row.get("BalQty") or "0")


@dbsec_app.command("auth-status")
def dbsec_auth_status() -> None:
    """Show credential metadata without issuing a token or revealing secrets."""
    settings, store = _context()
    alias = _account_alias(settings, store)
    expiry_raw = store.setting("dbsec_credential_expire_date")
    expiry = date.fromisoformat(expiry_raw) if expiry_raw else None
    token_expiry_raw = get_secret(alias, "access_token_expires_at")
    try:
        token_valid = bool(token_expiry_raw and datetime.fromisoformat(token_expiry_raw) > datetime.now(timezone.utc) + timedelta(minutes=5))
    except ValueError:
        token_valid = False
    typer.echo(
        canonical_json(
            {
                "credentials_present": bool(get_secret(alias, "app_key") and get_secret(alias, "app_secret")),
                "credential_environment": store.setting("dbsec_credential_env", "unknown"),
                "credential_expired": expiry < date.today() if expiry else None,
                "cached_token_valid": token_valid,
            }
        )
    )


@dbsec_app.command("holdings")
def dbsec_holdings() -> None:
    """List overseas symbols and quantities; never emits the raw response."""
    broker, _, _ = _read_only_broker()
    try:
        rows = broker.holdings()
    except BrokerError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for row in rows:
        typer.echo(f"{_symbol(row)}\t{_quantity(row)}")
    typer.echo(f"holdings={len(rows)}")


@dbsec_app.command("balance")
def dbsec_balance() -> None:
    """Show the minimal safe overseas balance view."""
    broker, _, _ = _read_only_broker()
    try:
        rows = broker.holdings()
    except BrokerError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for row in rows:
        currency = str(row.get("CrcyCode") or row.get("FcurrCode") or "USD")
        typer.echo(f"{currency}\t{_symbol(row)}\t{_quantity(row)}")
    typer.echo(f"balance_rows={len(rows)}")


@dbsec_app.command("transaction-history")
def dbsec_transaction_history(start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    broker, _, _ = _read_only_broker()
    start_date, end_date = _date_value(start, "start"), _date_value(end, "end")
    if start_date > end_date:
        raise typer.BadParameter("start must be on or before end")
    try:
        rows = broker.transaction_history(start_date, end_date)
    except BrokerError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for row in rows:
        typer.echo(f"{row.get('OrdDt', '-')}\t{_symbol(row)}\t{row.get('AstkBnsTpCode', '-')}\t{row.get('AstkExecQty', '0')}")
    typer.echo(f"transactions={len(rows)}")


@dbsec_app.command("current-price")
def dbsec_current_price(symbol: str = typer.Option(...)) -> None:
    broker, _, _ = _read_only_broker()
    selected = symbol.upper()
    try:
        price = broker.current_price(selected, market_code=MARKET_CODES.get(selected, "FN"))
    except BrokerError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"{selected}\t{price}")


@dbsec_app.command("daily-chart")
def dbsec_daily_chart(symbol: str = typer.Option(...), start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    broker, _, _ = _read_only_broker()
    selected = symbol.upper()
    start_date, end_date = _date_value(start, "start"), _date_value(end, "end")
    if start_date > end_date:
        raise typer.BadParameter("start must be on or before end")
    try:
        rows = broker.daily_candles(selected, start_date, end_date, market_code=MARKET_CODES.get(selected, "FN"))
    except BrokerError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for row in rows:
        typer.echo(f"{row['date']}\t{row['open']}\t{row['high']}\t{row['low']}\t{row['close']}\t{row['volume']}")
    typer.echo(f"candles={len(rows)}")


@app.command()
def setup(
    account_alias: str = typer.Option("default"),
    save_access_token: bool = typer.Option(False, help="Prompt for and save a temporary access token in the OS keychain."),
    save_api_credentials: bool = typer.Option(False, help="Prompt for the app key and secret required for automatic OAuth renewal."),
    import_env_credentials: bool = typer.Option(False, help="Import DB_APPKEY/DB_APPSECRET from .env into the OS keychain."),
    credential_expire_date: str | None = typer.Option(None, help="DB-issued APP KEY expiry in YYYYMMDD format."),
    tqqq_capital: str | None = typer.Option(None, help="Create the default OFF TQQQ profile with this USD capital."),
    soxl_capital: str | None = typer.Option(None, help="Create the default OFF SOXL profile with this USD capital."),
    tqqq_division: int = typer.Option(40, min=20, max=40),
    soxl_division: int = typer.Option(40, min=20, max=40),
) -> None:
    """Initialize the local database and optionally save credentials securely."""
    settings, store = _context()
    store.set_setting("account_alias", account_alias)
    store.set_setting("emergency_stop", "true")
    if save_api_credentials and import_env_credentials:
        raise typer.BadParameter("choose either --save-api-credentials or --import-env-credentials")
    if save_access_token:
        token = getpass("DB Securities access token: ")
        store_secret(account_alias, "access_token", token)
    if save_api_credentials:
        app_key = getpass("DB Securities app key: ")
        app_secret = getpass("DB Securities app secret: ")
        expiry_text = credential_expire_date or typer.prompt("DB Securities APP KEY expiry (YYYYMMDD)")
        try:
            expiry = datetime.strptime(expiry_text, "%Y%m%d").date()
        except ValueError as exc:
            raise typer.BadParameter("--credential-expire-date must use YYYYMMDD") from exc
        if expiry < date.today():
            raise typer.BadParameter("DB Securities app credentials have expired")
        store_secret(account_alias, "app_key", app_key)
        store_secret(account_alias, "app_secret", app_secret)
        store.set_setting("dbsec_credential_env", "real")
        store.set_setting("dbsec_credential_expire_date", expiry.isoformat())
    if import_env_credentials:
        if settings.db_appkey is None or settings.db_appsecret is None:
            raise typer.BadParameter("DB_APPKEY and DB_APPSECRET must both be set in .env")
        credential_env = (settings.db_credential_env or "").strip().lower()
        if credential_env != "real":
            raise typer.BadParameter("DB_ENV must be real for the v1 production endpoint")
        try:
            expiry = datetime.strptime(settings.db_expire_date or "", "%Y%m%d").date()
        except ValueError as exc:
            raise typer.BadParameter("DB_EXPIRE_DATE must use YYYYMMDD") from exc
        if expiry < date.today():
            raise typer.BadParameter("DB Securities app credentials have expired")
        store_secret(account_alias, "app_key", settings.db_appkey.get_secret_value())
        store_secret(account_alias, "app_secret", settings.db_appsecret.get_secret_value())
        store.set_setting("dbsec_credential_env", credential_env)
        store.set_setting("dbsec_credential_expire_date", expiry.isoformat())
        typer.echo("Imported DB Securities credentials into the OS keychain. Remove DB_APPKEY and DB_APPSECRET from .env.")
    for profile_id, symbol, capital, division in (
        ("tqqq", "TQQQ", tqqq_capital, tqqq_division),
        ("soxl", "SOXL", soxl_capital, soxl_division),
    ):
        if capital is None:
            continue
        store.create_profile(
            StrategyProfile(
                profile_id=profile_id,
                symbol=symbol,
                division_count=division,
                capital=_decimal_value(capital, f"{symbol} capital"),
                account_alias=account_alias,
                status="OFF",
            )
        )
    typer.echo(f"Initialized {settings.db_path}. Emergency stop is ON.")


@profile_app.command("create")
def profile_create(
    profile_id: str,
    symbol: str = typer.Option(...),
    division: int = typer.Option(..., min=20, max=40),
    capital: str = typer.Option(..., help="US-dollar strategy capital. KRW settlement is not live-eligible in v1."),
    effective_from: str = typer.Option(date.today().isoformat()),
) -> None:
    settings, store = _context()
    profile = StrategyProfile(
        profile_id=profile_id,
        symbol=symbol,
        division_count=division,
        capital=_decimal_value(capital, "capital"),
        account_alias=store.setting("account_alias", settings.account_alias) or settings.account_alias,
        status="OFF",
        effective_from=_date_value(effective_from, "effective_from"),
    )
    store.create_profile(profile)
    label = "experimental-preview-only" if division == 30 else "live-candidate"
    typer.echo(f"Created {profile_id}: {profile.symbol}/{division} ({label})")


@profile_app.command("list")
def profile_list() -> None:
    _, store = _context()
    for profile in store.list_profiles():
        typer.echo(f"{profile.profile_id}\t{profile.symbol}\t{profile.division_count}\t{profile.capital}\t{profile.status}")


@capability_app.command("verify")
def capability_verify(
    opposing_loc_confirmed: bool = typer.Option(False, help="Set only after the documented testbed protocol passes."),
    rate_limits_confirmed: bool = typer.Option(False, help="Set only after every used TR rate is recorded."),
    live_order_tests_confirmed: bool = typer.Option(False, help="Set only after the instructor real-account acceptance protocol passes."),
    evidence: str = typer.Option("official documentation review"),
) -> None:
    _, store = _context()
    confirmed = {
        "us_stock_etf_order": "official order specification",
        "loc_order_type": "AstkOrdprcPtnCode=5",
        "moc_order_type": "AstkOrdprcPtnCode=6",
        "modify_cancel": "OrdTrdTpCode=1/2",
        "transaction_history": "official transaction-history endpoint",
        "balance_margin": "official balance-margin endpoint",
        "orderable_amount": "official able-orderqty endpoint and schema",
        "current_price_schema": "official overseas price workbook",
        "daily_chart_schema": "official overseas day-chart workbook",
        "oauth_client_credentials": "official client-credentials token and revoke workbooks",
    }
    for name, source in confirmed.items():
        store.set_capability(name, "확인됨", source)
    store.set_capability("supports_opposing_loc", "확인됨" if opposing_loc_confirmed else "확인 필요", evidence)
    store.set_capability("rate_limits", "확인됨" if rate_limits_confirmed else "확인 필요", evidence)
    for name in ("live_order_test_loc", "live_order_test_moc", "live_cancel_test", "live_partial_fill_test", "live_timeout_reconciliation_test"):
        store.set_capability(name, "확인됨" if live_order_tests_confirmed else "확인 필요", evidence)
    for name in ("client_idempotency_key", "early_close_broker_cutoff"):
        if store.capability(name) is None:
            store.set_capability(name, "확인 필요", "not yet verified")
    typer.echo("Capability matrix updated. Live remains blocked unless all live gates pass.")


def _parse_closes(values: str) -> tuple[Decimal, ...]:
    return tuple(Decimal(item.strip()) for item in values.split(",") if item.strip())[-5:]


def _decimal_value(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise typer.BadParameter(f"{name} must be a decimal number") from exc
    if parsed <= 0:
        raise typer.BadParameter(f"{name} must be positive")
    return parsed


def _date_value(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{name} must use YYYY-MM-DD") from exc


@app.command()
def preview(
    profile_id: str,
    previous_close: str = typer.Option(...),
    session_date: str = typer.Option(date.today().isoformat()),
    completed_closes: str = typer.Option(""),
) -> None:
    _, store = _context()
    parsed_date = _date_value(session_date, "session_date")
    result: dict[str, object] = {"session_date": parsed_date.isoformat(), "profile_id": profile_id}
    for phase in (Phase.SELL, Phase.BUY):
        intents = preview_phase(store, profile_id, parsed_date, _decimal_value(previous_close, "previous_close"), phase, _parse_closes(completed_closes))
        result[phase.value] = [intent.to_dict() for intent in intents]
    typer.echo(canonical_json(result))


def _run_phase(
    profile_id: str,
    previous_close: Decimal | None,
    session_date: date,
    completed_closes: str,
    phase: Phase,
    environment: Environment,
    *,
    emit: bool = True,
) -> dict[str, object]:
    settings, store = _context()
    profile = store.get_profile(profile_id)
    state = store.get_state(profile_id)
    parsed_closes = _parse_closes(completed_closes)
    if environment != Environment.LIVE:
        raise typer.BadParameter("paper/preview execution was removed in 0.2.0; use app preview for calculation only")
    broker = _live_broker(settings, store, profile.account_alias)
    state = reconcile_dbsec(store, broker, profile, session_date)
    if state.reconciliation_required:
        raise typer.BadParameter("Broker reconciliation failed; no new order may be generated")
    if previous_close is None or not parsed_closes:
        candles = broker.daily_candles(profile.symbol, session_date - timedelta(days=14), session_date - timedelta(days=1))
        if not candles:
            raise typer.BadParameter("DB Securities returned no completed daily candles")
        parsed_closes = tuple(item["close"] for item in candles[-5:])
        previous_close = candles[-1]["close"]
    if previous_close is None:
        raise typer.BadParameter("completed DB Securities market data is required")
    intents, inserted = plan_phase(store, profile_id, session_date, previous_close, phase, parsed_closes)
    pending = store.pending_intents(profile_id, session_date, phase)
    state = store.get_state(profile_id)
    submitted = execute_intents(
        store,
        broker,
        profile,
        state,
        pending,
        environment,
        ExecutionLimits(settings.max_order_notional_usd, settings.max_daily_notional_usd),
    )
    if submitted:
        try:
            reconcile_dbsec(store, broker, profile, session_date)
        except BrokerError:
            store.set_profile_status(profile_id, "LOCKED")
            latest = store.get_state(profile_id)
            if not latest.reconciliation_required:
                store.save_state(latest.evolved(reconciliation_required=True), latest.version)
            raise
    snapshot_cycle_session(store, profile, store.get_state(profile_id), session_date, market_price=previous_close)
    result: dict[str, object] = {"generated": len(intents), "new_intents": inserted, "submitted": submitted, "environment": environment}
    if emit:
        typer.echo(canonical_json(result))
    return result


@run_app.command("sell-phase")
def run_sell_phase(
    profile_id: str,
    previous_close: str | None = typer.Option(None),
    session_date: str = typer.Option(date.today().isoformat()),
    completed_closes: str = typer.Option(""),
) -> None:
    _run_phase(
        profile_id,
        _decimal_value(previous_close, "previous_close") if previous_close is not None else None,
        _date_value(session_date, "session_date"),
        completed_closes,
        Phase.SELL,
        Environment.LIVE,
    )


@run_app.command("buy-phase")
def run_buy_phase(
    profile_id: str,
    previous_close: str | None = typer.Option(None),
    session_date: str = typer.Option(date.today().isoformat()),
    completed_closes: str = typer.Option(""),
) -> None:
    _run_phase(
        profile_id,
        _decimal_value(previous_close, "previous_close") if previous_close is not None else None,
        _date_value(session_date, "session_date"),
        completed_closes,
        Phase.BUY,
        Environment.LIVE,
    )


@app.command()
def reconcile(
    profile_id: str | None = typer.Argument(None),
    profile: str | None = typer.Option(None, "--profile"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    settings, store = _context()
    selected = profile or profile_id
    if not selected:
        raise typer.BadParameter("PROFILE or --profile is required")
    selected_profile = store.get_profile(selected)
    result = reconcile_dbsec(store, _live_broker(settings, store, selected_profile.account_alias), selected_profile, date.today())
    data = {"profile_id": selected, "status": "RECONCILIATION_REQUIRED" if result.reconciliation_required else "OK"}
    typer.echo(envelope_json(data) if json_output else data["status"])


@orders_app.command("list")
def orders_list(profile: str | None = typer.Option(None, "--profile"), json_output: bool = typer.Option(False, "--json")) -> None:
    _, store = _context()
    rows = store.list_orders(profile)
    if json_output:
        typer.echo(envelope_json([dict(row) for row in rows]))
        return
    for row in rows:
        typer.echo(f"{row['broker_order_no']}\t{row['intent_id']}\t{row['status']}\t{row['requested_qty']}\t{row['remaining_qty']}")


@orders_app.command("cancel")
def orders_cancel(broker_order_no: str, profile_id: str, confirm: bool = typer.Option(False, "--confirm")) -> None:
    if not confirm:
        raise typer.BadParameter("Pass --confirm after reviewing the broker order")
    settings, store = _context()
    profile = store.get_profile(profile_id)
    row = store.get_order(broker_order_no)
    intent = store.get_intent(row["intent_id"])
    broker = _live_broker(settings, store, profile.account_alias)
    result = broker.cancel_order_for_symbol(profile.symbol, broker_order_no, intent)
    store.update_order_status(
        broker_order_no,
        result.status,
        row["filled_qty"],
        row["remaining_qty"],
        row["account_alias"],
        date.fromisoformat(row["order_date"]),
    )
    store.audit("ORDER_CANCEL_REQUESTED", {"broker_order_no": broker_order_no, "intent_id": intent.intent_id})
    typer.echo(result.status)


LIVE_RUNTIME_CAPABILITIES = (
    "oauth_client_credentials",
    "rate_limits",
    "supports_opposing_loc",
    "live_order_test_loc",
    "live_order_test_moc",
    "live_cancel_test",
    "live_partial_fill_test",
    "live_timeout_reconciliation_test",
)


def _readiness_data(store: StateStore, profile_id: str) -> dict[str, object]:
    profile = store.get_profile(profile_id)
    state = store.get_state(profile_id)
    expiry_raw = store.setting("dbsec_credential_expire_date")
    try:
        credential_unexpired = bool(expiry_raw and date.fromisoformat(expiry_raw) >= date.today())
    except ValueError:
        credential_unexpired = False
    weather_rows = store.weather_history(profile.symbol, 1)
    expected_weather_date = latest_completed_session()
    checks: dict[str, bool] = {
        "profile_not_locked": profile.status.upper() != "LOCKED",
        "division_live_eligible": profile.division_count in {20, 40},
        "credentials_present": bool(get_secret(profile.account_alias, "app_key") and get_secret(profile.account_alias, "app_secret")),
        "credential_unexpired": credential_unexpired,
        "cron_verified": store.setting("hermes_cron_verified", "false") == "true",
        "emergency_stop_clear": store.setting("emergency_stop", "true") == "false",
        "reconciliation_clear": not state.reconciliation_required,
        "weather_fresh": bool(weather_rows and date.fromisoformat(weather_rows[0]["session_date"]) >= expected_weather_date),
    }
    for capability in LIVE_RUNTIME_CAPABILITIES:
        checks[f"capability:{capability}"] = store.capability(capability) == "확인됨"
    failures = [name for name, passed in checks.items() if not passed]
    return {"profile_id": profile_id, "status": profile.status, "ready": not failures, "checks": checks, "failures": failures}


def _complete_readiness(settings: Settings, store: StateStore, profile_id: str) -> tuple[dict[str, object], DbSecBroker | None]:
    result = _readiness_data(store, profile_id)
    if not result["ready"]:
        return result, None
    selected = store.get_profile(profile_id)
    checks = result["checks"]
    assert isinstance(checks, dict)
    try:
        broker = _live_broker(settings, store, selected.account_alias)
        state = reconcile_dbsec(store, broker, selected, date.today())
        holding = broker.holding(selected.symbol)
        first_on = not store.list_position_cycles(profile_id)
        flat_for_first_on = not first_on or holding is None or int(Decimal(str(holding.get("AstkExecBaseQty") or 0))) == 0
        recent_records = broker.transaction_history(date.today() - timedelta(days=365), date.today(), selected.symbol) if first_on else []
        no_open_orders_for_first_on = not first_on or not any(int(Decimal(str(row.get("AstkOrdRmqty") or 0))) > 0 for row in recent_records)
        price = broker.current_price(selected.symbol, market_code=MARKET_CODES[selected.symbol])
        available_amount, _ = broker.orderable_amount(selected.symbol, Side.BUY, price, "2")
        checks.update(
            {
                "broker_reconciliation": not state.reconciliation_required,
                "first_on_target_flat": flat_for_first_on,
                "first_on_no_open_orders": no_open_orders_for_first_on,
                "settled_usd_orderable": available_amount > 0,
            }
        )
    except (BrokerError, OAuthError, ValueError) as exc:
        checks["broker_reconciliation"] = False
        result["broker_error"] = str(exc)
        broker = None
    failures = [name for name, passed in checks.items() if not passed]
    result["failures"] = failures
    result["ready"] = not failures
    return result, broker


@automation_app.command("readiness")
def automation_readiness(profile: str = typer.Option(..., "--profile")) -> None:
    settings, store = _context()
    result, _ = _complete_readiness(settings, store, profile)
    typer.echo(envelope_json(result, ok=bool(result["ready"]), errors=[] if result["ready"] else [{"code": "READINESS_FAILED", "details": result["failures"]}]))
    if not result["ready"]:
        raise typer.Exit(2)


@automation_app.command("status")
def automation_status(profile: str | None = typer.Argument(None), json_output: bool = typer.Option(True, "--json/--text")) -> None:
    _, store = _context()
    profiles = [store.get_profile(profile)] if profile else store.list_profiles()
    data = [
        {
            "profile_id": item.profile_id,
            "symbol": item.symbol,
            "status": item.status,
            "reconciliation_required": store.get_state(item.profile_id).reconciliation_required,
            "unresolved_order_count": len(store.unresolved_orders(item.profile_id)),
        }
        for item in profiles
    ]
    typer.echo(envelope_json(data) if json_output else canonical_json(data))


@automation_app.command("on")
def automation_on(profile: str = typer.Option(..., "--profile"), cron_verified: bool = typer.Option(False, "--cron-verified")) -> None:
    settings, store = _context()
    if cron_verified:
        store.set_setting("hermes_cron_verified", "true")
    static, broker = _complete_readiness(settings, store, profile)
    if not static["ready"]:
        typer.echo(envelope_json(static, ok=False, errors=[{"code": "READINESS_FAILED", "details": static["failures"]}]))
        raise typer.Exit(2)
    assert broker is not None
    store.set_profile_status(profile, "ON")
    typer.echo(envelope_json({"profile_id": profile, "status": "ON"}))


@automation_app.command("off")
def automation_off(profile: str = typer.Option(..., "--profile")) -> None:
    settings, store = _context()
    selected = store.get_profile(profile)
    store.set_profile_status(profile, "OFF")
    unresolved = store.unresolved_orders(profile)
    cancelled: list[str] = []
    if unresolved:
        broker = _live_broker(settings, store, selected.account_alias)
        try:
            for row in unresolved:
                if row["status"] in {"UNKNOWN", "CANCEL_REQUESTED"}:
                    continue
                intent = store.get_intent(row["intent_id"])
                broker.cancel_order_for_symbol(selected.symbol, row["broker_order_no"], intent)
                store.update_order_status(
                    row["broker_order_no"],
                    "CANCEL_REQUESTED",
                    row["filled_qty"],
                    row["remaining_qty"],
                    row["account_alias"],
                    date.fromisoformat(row["order_date"]),
                )
                cancelled.append(row["broker_order_no"])
            state = reconcile_dbsec(store, broker, selected, date.today())
            if state.reconciliation_required or store.unresolved_orders(profile):
                raise AmbiguousOrderError("cancellation could not be confirmed")
        except (AmbiguousOrderError, BrokerError, OAuthError) as exc:
            store.set_profile_status(profile, "LOCKED")
            current = store.get_state(profile)
            if not current.reconciliation_required:
                store.save_state(current.evolved(reconciliation_required=True), current.version)
            typer.echo(envelope_json({"profile_id": profile, "status": "LOCKED"}, ok=False, errors=[{"code": "CANCEL_RECONCILIATION_UNKNOWN", "message": str(exc)}]))
            raise typer.Exit(2) from exc
    if store.has_unknown_intents(profile):
        store.set_profile_status(profile, "LOCKED")
        typer.echo(envelope_json({"profile_id": profile, "status": "LOCKED"}, ok=False, errors=[{"code": "UNKNOWN_ORDER_REQUIRES_RECONCILIATION"}]))
        raise typer.Exit(2)
    typer.echo(envelope_json({"profile_id": profile, "status": "OFF", "cancelled": cancelled}))


@automation_app.command("tick")
def automation_tick(all_profiles: bool = typer.Option(False, "--all"), quiet_when_idle: bool = typer.Option(False, "--quiet-when-idle")) -> None:
    now = datetime.now(NEW_YORK)
    try:
        schedule = session_schedule(now.date())
    except ValueError:
        if not quiet_when_idle:
            typer.echo(envelope_json({"actions": []}))
        return
    phase = Phase.SELL if schedule.sell_phase_at <= now < schedule.sell_phase_at + timedelta(minutes=15) else Phase.BUY if schedule.buy_phase_at <= now < schedule.buy_phase_at + timedelta(minutes=15) else None
    if phase is None:
        if not quiet_when_idle:
            typer.echo(envelope_json({"actions": []}))
        return
    _, store = _context()
    profiles = [item for item in store.list_profiles() if item.status == "ON"]
    if not all_profiles and len(profiles) > 1:
        profiles = profiles[:1]
    actions: list[dict[str, str]] = []
    for item in profiles:
        claim = f"{item.profile_id}:{schedule.session_date}:{phase.value}"
        if not store.claim_automation(claim):
            continue
        try:
            result = _run_phase(item.profile_id, None, schedule.session_date, "", phase, Environment.LIVE, emit=False)
            store.finish_automation(claim, "COMPLETED")
            actions.append({"profile_id": item.profile_id, "phase": phase.value, "submitted": str(len(result["submitted"]))})
        except Exception:
            store.finish_automation(claim, "FAILED")
            raise
    if actions or not quiet_when_idle:
        typer.echo(envelope_json({"actions": actions}))


@capital_app.command("scan")
def capital_scan() -> None:
    _, store = _context()
    if store.capability("cash_transactions") != "확인됨":
        typer.echo(envelope_json(None, ok=False, errors=[{"code": "CAPABILITY_NOT_VERIFIED", "message": "DB Securities cash transaction endpoint is not verified"}]))
        raise typer.Exit(2)
    typer.echo(envelope_json(None, ok=False, errors=[{"code": "CAPABILITY_ADAPTER_NOT_IMPLEMENTED", "message": "Verified response fixtures and field mapping are required before enabling capital scan"}]))
    raise typer.Exit(2)


@capital_app.command("status")
def capital_status() -> None:
    settings, store = _context()
    alias = _account_alias(settings, store)
    typer.echo(envelope_json({"account_alias": alias, "unallocated_settled_usd": str(available_settled_usd(store, alias)), "events": [dict(row) for row in store.capital_events(alias)]}))


@capital_app.command("propose")
def capital_propose(profile: str = typer.Option(..., "--profile"), amount: str = typer.Option(...)) -> None:
    _, store = _context()
    selected = store.get_profile(profile)
    parsed = _decimal_value(amount, "amount")
    available = available_settled_usd(store, selected.account_alias)
    ok = parsed <= available
    typer.echo(envelope_json({"profile_id": profile, "amount": str(parsed), "available": str(available), "choices": ["current_cycle", "next_cycle"]}, ok=ok, errors=[] if ok else [{"code": "ALLOCATION_EXCEEDS_SETTLED_USD"}]))


@capital_app.command("apply")
def capital_apply(profile: str = typer.Option(..., "--profile"), amount: str = typer.Option(...), timing: str = typer.Option(...)) -> None:
    _, store = _context()
    try:
        result = apply_allocation(store, profile, _decimal_value(amount, "amount"), timing)
    except CapitalError as exc:
        typer.echo(envelope_json(None, ok=False, errors=[{"code": str(exc)}]))
        raise typer.Exit(2) from exc
    typer.echo(envelope_json(result))


@weather_app.command("update")
def weather_update(symbol: str = typer.Option(...), json_output: bool = typer.Option(True, "--json/--text")) -> None:
    symbol = symbol.upper()
    if symbol not in SIGNAL_SYMBOLS:
        raise typer.BadParameter("symbol must be TQQQ or SOXL")
    broker, store, _ = _read_only_broker()
    end = latest_completed_session()
    start = end - timedelta(days=800)
    series: dict[str, object] = {}
    try:
        collection = collect_market_data(broker)
        for item in (symbol, SIGNAL_SYMBOLS[symbol], "SPY"):
            rows = broker.daily_candles(item, start, end, market_code=MARKET_CODES[item])
            series[item] = candles_from_rows(rows)
        snapshots = compute_weather_history(symbol, series)  # type: ignore[arg-type]
        for snapshot in snapshots:
            store.save_weather(snapshot)
    except (BrokerError, WeatherDataError, ValueError) as exc:
        typer.echo(envelope_json(None, ok=False, errors=[{"code": "WEATHER_UPDATE_FAILED", "message": str(exc)}]))
        raise typer.Exit(2) from exc
    data = {
        "symbol": symbol,
        "ruleset_version": "regime-weather-1",
        "saved": len(snapshots),
        "latest": snapshots[-1] if snapshots else None,
        "market_data": collection,
    }
    typer.echo(envelope_json(data) if json_output else canonical_json(data))


@weather_app.command("current")
def weather_current(symbol: str = typer.Option(...), json_output: bool = typer.Option(True, "--json/--text")) -> None:
    _, store = _context()
    rows = store.weather_history(symbol, 1)
    ok = bool(rows)
    output = envelope_json(rows[0] if rows else None, ok=ok, errors=[] if ok else [{"code": "WEATHER_NOT_AVAILABLE"}])
    typer.echo(output if json_output else canonical_json(rows[0] if rows else {}))


@weather_app.command("history")
def weather_history(symbol: str = typer.Option(...), limit: int = typer.Option(250, min=1), json_output: bool = typer.Option(True, "--json/--text")) -> None:
    _, store = _context()
    rows = store.weather_history(symbol, limit)
    typer.echo(envelope_json(rows) if json_output else canonical_json(rows))


def _profile_status_payload(store: StateStore, profile_id: str) -> dict[str, object]:
    profile = store.get_profile(profile_id)
    state = store.get_state(profile_id)
    cycles = store.list_position_cycles(profile_id)
    current_cycle = next((dict(row) for row in cycles if row["status"] == "OPEN"), None)
    return {
        "profile_id": profile.profile_id,
        "symbol": profile.symbol,
        "automation_status": profile.status,
        "division_count": profile.division_count,
        "cycle": current_cycle,
        "cycle_id": state.cycle_id,
        "t": str(state.t),
        "mode": state.mode.value,
        "quantity": state.quantity,
        "avg_cost": str(state.avg_cost),
        "cash": str(state.cash),
        "invested": str(state.cost_basis),
        "reconciliation_required": state.reconciliation_required,
    }


@position_app.command("status")
def position_status(profile: str | None = typer.Argument(None), json_output: bool = typer.Option(True, "--json/--text")) -> None:
    _, store = _context()
    ids = [profile] if profile else [item.profile_id for item in store.list_profiles()]
    data = [_profile_status_payload(store, item) for item in ids]
    typer.echo(envelope_json(data) if json_output else canonical_json(data))


@position_app.command("cycles")
def position_cycles(profile: str | None = typer.Argument(None), json_output: bool = typer.Option(True, "--json/--text")) -> None:
    _, store = _context()
    rows = [dict(row) for row in store.list_position_cycles(profile)]
    typer.echo(envelope_json(rows) if json_output else canonical_json(rows))


@position_app.command("sessions")
def position_sessions(profile: str, cycle: int = typer.Option(..., "--cycle", min=1), json_output: bool = typer.Option(True, "--json/--text")) -> None:
    _, store = _context()
    rows = [dict(row) for row in store.list_cycle_sessions(profile, cycle)]
    typer.echo(envelope_json(rows) if json_output else canonical_json(rows))


@report_app.command("daily")
def report_daily(session_date: str = typer.Option("latest", "--session-date"), json_output: bool = typer.Option(True, "--json/--text")) -> None:
    _, store = _context()
    selected_date = latest_completed_session().isoformat() if session_date == "latest" else _date_value(session_date, "session_date").isoformat()
    profiles: list[dict[str, object]] = []
    for profile in store.list_profiles():
        status = _profile_status_payload(store, profile.profile_id)
        orders = [dict(row) for row in store.list_orders(profile.profile_id) if row["order_date"] == selected_date]
        weather = store.weather_history(profile.symbol, 1)
        status.update(
            {
                "orders": orders,
                "order_count": len(orders),
                "fill_count": sum(1 for row in orders if row["filled_qty"]),
                "cancel_count": sum(1 for row in orders if str(row["status"]).startswith("CANCEL")),
                "weather": weather[0] if weather else None,
                "unallocated_settled_usd": str(available_settled_usd(store, profile.account_alias)),
                "warnings": [code for code, active in (("UNKNOWN_ORDER", any(row["status"] == "UNKNOWN" for row in orders)), ("LOCKED", profile.status == "LOCKED")) if active],
            }
        )
        profiles.append(status)
    data = {"session_date": selected_date, "profiles": profiles}
    typer.echo(envelope_json(data) if json_output else canonical_json(data))


@dashboard_app.command("start")
def dashboard_start() -> None:
    root = Path(__file__).resolve().parents[2] / "dashboard"
    executable = "npm.cmd" if sys.platform == "win32" else "npm"
    raise typer.Exit(subprocess.run([executable, "run", "dev"], cwd=root, check=False).returncode)


@emergency_app.command("on")
def emergency_on() -> None:
    _, store = _context()
    store.set_setting("emergency_stop", "true")
    typer.echo("Emergency stop ON")


@emergency_app.command("off")
def emergency_off() -> None:
    _, store = _context()
    store.set_setting("emergency_stop", "false")
    typer.echo("Emergency stop OFF")


@app.command()
def replay(profile_id: str, source: Path) -> None:
    _, store = _context()
    typer.echo(canonical_json(replay_file(store.get_profile(profile_id), source)))


@app.command()
def backtest(profile_id: str, source: Path) -> None:
    """Replay deterministic daily event vectors; alias of replay for v1."""
    replay(profile_id, source)


@backup_app.command("create")
def backup_create(target: Path) -> None:
    _, store = _context()
    typer.echo(str(store.backup(target)))


@backup_app.command("restore")
def backup_restore(source: Path, confirm: bool = typer.Option(False, "--confirm")) -> None:
    if not confirm:
        raise typer.BadParameter("Pass --confirm to replace the active database")
    _, store = _context()
    store.restore(source)
    typer.echo("Restored")


@app.command()
def diagnostics(output: Path = typer.Option(Path("diagnostics/report.json")), redacted: bool = typer.Option(True, "--redacted/--unsafe-unredacted")) -> None:
    settings, store = _context()
    report = {
        "generated_at": datetime.now(timezone.utc),
        "python": sys.version,
        "db_path": str(settings.db_path),
        "account_alias": store.setting("account_alias", settings.account_alias) or settings.account_alias,
        "profiles": [asdict(profile) for profile in store.list_profiles()],
        "automation": {profile.profile_id: profile.status for profile in store.list_profiles()},
        "emergency_stop": store.setting("emergency_stop", "true"),
    }
    payload = redact(report) if redacted else report
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(payload), encoding="utf-8")
    typer.echo(str(output))


if __name__ == "__main__":
    app()

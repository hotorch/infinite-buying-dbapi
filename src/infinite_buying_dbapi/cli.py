from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from getpass import getpass
from pathlib import Path

import typer

from .auth import DbSecTokenManager
from .broker import DbSecBroker, PaperBroker, PreviewBroker
from .config import Settings
from .execution import ExecutionLimits, execute_intents
from .market_calendar import NEW_YORK, session_schedule
from .models import Environment, Phase, StrategyProfile, canonical_json
from .rate_limit import DbSecRateLimiter
from .reconciliation import reconcile_dbsec
from .replay import replay_file
from .security import redact, store_secret
from .service import plan_phase
from .store import StateStore

app = typer.Typer(no_args_is_help=True, help="Pure V4 + DB Securities operator CLI")
profile_app = typer.Typer(no_args_is_help=True)
capability_app = typer.Typer(no_args_is_help=True)
run_app = typer.Typer(no_args_is_help=True)
orders_app = typer.Typer(no_args_is_help=True)
live_app = typer.Typer(no_args_is_help=True)
emergency_app = typer.Typer(no_args_is_help=True)
backup_app = typer.Typer(no_args_is_help=True)
scheduler_app = typer.Typer(no_args_is_help=True)
app.add_typer(profile_app, name="profile")
app.add_typer(capability_app, name="capability")
app.add_typer(run_app, name="run")
app.add_typer(orders_app, name="orders")
app.add_typer(live_app, name="live")
app.add_typer(emergency_app, name="emergency-stop")
app.add_typer(backup_app, name="backup")
app.add_typer(scheduler_app, name="scheduler")


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
    return DbSecBroker(settings.dbsec_base_url, token, settings.request_timeout_seconds, before_request=limiter.wait)


@app.command()
def setup(
    account_alias: str = typer.Option("default"),
    save_access_token: bool = typer.Option(False, help="Prompt for and save a temporary access token in Windows Credential Manager."),
    save_api_credentials: bool = typer.Option(False, help="Prompt for the app key and secret required for automatic OAuth renewal."),
) -> None:
    """Initialize the local database and optionally save a token securely."""
    settings, store = _context()
    store.set_setting("account_alias", account_alias)
    store.set_setting("emergency_stop", "true")
    if save_access_token:
        token = getpass("DB Securities access token: ")
        store_secret(account_alias, "access_token", token)
    if save_api_credentials:
        store_secret(account_alias, "app_key", getpass("DB Securities app key: "))
        store_secret(account_alias, "app_secret", getpass("DB Securities app secret: "))
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
        "paper_order": "official documentation states test account support",
    }
    for name, source in confirmed.items():
        store.set_capability(name, "확인됨", source)
    store.set_capability("supports_opposing_loc", "확인됨" if opposing_loc_confirmed else "확인 필요", evidence)
    store.set_capability("rate_limits", "확인됨" if rate_limits_confirmed else "확인 필요", evidence)
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
        intents, _ = plan_phase(store, profile_id, parsed_date, _decimal_value(previous_close, "previous_close"), phase, _parse_closes(completed_closes))
        result[phase.value] = [intent.to_dict() for intent in intents]
    typer.echo(canonical_json(result))


def _run_phase(profile_id: str, previous_close: Decimal | None, session_date: date, completed_closes: str, phase: Phase, environment: Environment) -> None:
    settings, store = _context()
    profile = store.get_profile(profile_id)
    state = store.get_state(profile_id)
    parsed_closes = _parse_closes(completed_closes)
    if environment == Environment.PREVIEW:
        broker = PreviewBroker()
    elif environment == Environment.PAPER:
        broker = PaperBroker()
    else:
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
        raise typer.BadParameter("--previous-close is required for preview and paper environments")
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
    typer.echo(canonical_json({"generated": len(intents), "new_intents": inserted, "submitted": submitted, "environment": environment}))


@run_app.command("sell-phase")
def run_sell_phase(
    profile_id: str,
    previous_close: str | None = typer.Option(None),
    session_date: str = typer.Option(date.today().isoformat()),
    completed_closes: str = typer.Option(""),
    environment: Environment = typer.Option(Environment.PREVIEW),
) -> None:
    _run_phase(
        profile_id,
        _decimal_value(previous_close, "previous_close") if previous_close is not None else None,
        _date_value(session_date, "session_date"),
        completed_closes,
        Phase.SELL,
        environment,
    )


@run_app.command("buy-phase")
def run_buy_phase(
    profile_id: str,
    previous_close: str | None = typer.Option(None),
    session_date: str = typer.Option(date.today().isoformat()),
    completed_closes: str = typer.Option(""),
    environment: Environment = typer.Option(Environment.PREVIEW),
) -> None:
    _run_phase(
        profile_id,
        _decimal_value(previous_close, "previous_close") if previous_close is not None else None,
        _date_value(session_date, "session_date"),
        completed_closes,
        Phase.BUY,
        environment,
    )


@app.command()
def reconcile(profile_id: str, broker_quantity: int | None = typer.Option(None, min=0), environment: Environment = typer.Option(Environment.PREVIEW)) -> None:
    settings, store = _context()
    profile = store.get_profile(profile_id)
    if environment == Environment.LIVE:
        result = reconcile_dbsec(store, _live_broker(settings, store, profile.account_alias), profile, date.today())
        typer.echo("RECONCILIATION_REQUIRED" if result.reconciliation_required else "OK")
        return
    if broker_quantity is None:
        raise typer.BadParameter("--broker-quantity is required outside live DB Securities reconciliation")
    state = store.get_state(profile_id)
    mismatch = state.quantity != broker_quantity
    updated = state.evolved(reconciliation_required=mismatch)
    store.save_state(updated, state.version)
    store.audit(
        "RECONCILIATION",
        {"profile_id": profile_id, "local_quantity": state.quantity, "broker_quantity": broker_quantity, "status": "MISMATCH" if mismatch else "OK"},
    )
    typer.echo("RECONCILIATION_REQUIRED" if mismatch else "OK")


@orders_app.command("list")
def orders_list() -> None:
    _, store = _context()
    for row in store.list_orders():
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
    store.update_order_status(broker_order_no, result.status, result.filled_qty, result.remaining_qty)
    store.audit("ORDER_CANCEL_REQUESTED", {"broker_order_no": broker_order_no, "intent_id": intent.intent_id})
    typer.echo(result.status)


@live_app.command("enable")
def live_enable(legal_review_ack: bool = typer.Option(False), risk_disclosure_ack: bool = typer.Option(False)) -> None:
    _, store = _context()
    if not legal_review_ack or not risk_disclosure_ack:
        raise typer.BadParameter("Both legal review and risk disclosure acknowledgements are required")
    if store.capability("supports_opposing_loc") != "확인됨":
        raise typer.BadParameter("Sequential opposing LOC testbed protocol has not passed")
    if store.capability("oauth_client_credentials") != "확인됨" or store.capability("rate_limits") != "확인됨":
        raise typer.BadParameter("OAuth and every used TR rate limit must be verified")
    store.set_setting("legal_review_ack", "true")
    store.set_setting("risk_disclosure_ack", "true")
    store.set_setting("live_enabled", "true")
    typer.echo("Live installation gate enabled. Emergency stop and daily approval still apply.")


@live_app.command("approve-today")
def live_approve_today(session_date: str = typer.Option(date.today().isoformat())) -> None:
    settings, store = _context()
    parsed_date = _date_value(session_date, "session_date")
    account_alias = store.setting("account_alias", settings.account_alias) or settings.account_alias
    store.approve_live(account_alias, parsed_date)
    typer.echo(f"Approved {account_alias} for {parsed_date}")


@live_app.command("disable")
def live_disable() -> None:
    _, store = _context()
    store.set_setting("live_enabled", "false")
    typer.echo("Live disabled")


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


@scheduler_app.command("show")
def scheduler_show(session_date: str = typer.Option(date.today().isoformat()), buffer_minutes: int = typer.Option(5, min=1, max=30)) -> None:
    typer.echo(canonical_json(session_schedule(_date_value(session_date, "session_date"), buffer_minutes)))


@scheduler_app.command("tick")
def scheduler_tick(profile_id: str, environment: Environment = typer.Option(Environment.LIVE)) -> None:
    """Run a due phase once. Intended for a five-minute Windows scheduled task."""
    now = datetime.now(NEW_YORK)
    try:
        schedule = session_schedule(now.date())
    except ValueError:
        typer.echo("NO_SESSION")
        return
    due: Phase | None = None
    if schedule.sell_phase_at <= now < schedule.sell_phase_at + timedelta(minutes=15):
        due = Phase.SELL
    elif schedule.buy_phase_at <= now < schedule.buy_phase_at + timedelta(minutes=15):
        due = Phase.BUY
    if due is None:
        typer.echo("NOT_DUE")
        return
    _, store = _context()
    run_id = f"{profile_id}:{schedule.session_date}:{due.value}"
    if not store.claim_scheduler_run(run_id, schedule.session_date, due):
        typer.echo("ALREADY_RAN")
        return
    try:
        _run_phase(profile_id, None, schedule.session_date, "", due, environment)
    except Exception:
        store.finish_scheduler_run(run_id, "FAILED")
        raise
    store.finish_scheduler_run(run_id, "COMPLETED")


@scheduler_app.command("install")
def scheduler_install(profile_id: str, task_name: str = typer.Option("InfiniteBuyingDBAPI"), confirm: bool = typer.Option(False, "--confirm")) -> None:
    """Install a five-minute Windows task; the tick command enforces NYSE timing."""
    if not confirm:
        raise typer.BadParameter("Pass --confirm to create a Windows scheduled task")
    command = f'"{sys.executable}" -m infinite_buying_dbapi.cli scheduler tick {profile_id} --environment live'
    result = subprocess.run(
        ["schtasks.exe", "/Create", "/SC", "MINUTE", "/MO", "5", "/TN", task_name, "/TR", command, "/F"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise typer.BadParameter(f"Task Scheduler rejected the task: {result.stderr.strip()}")
    typer.echo(result.stdout.strip())


@app.command()
def diagnostics(output: Path = typer.Option(Path("diagnostics/report.json")), redacted: bool = typer.Option(True, "--redacted/--unsafe-unredacted")) -> None:
    settings, store = _context()
    report = {
        "generated_at": datetime.now(timezone.utc),
        "python": sys.version,
        "db_path": str(settings.db_path),
        "account_alias": store.setting("account_alias", settings.account_alias) or settings.account_alias,
        "profiles": [asdict(profile) for profile in store.list_profiles()],
        "live_enabled": store.setting("live_enabled", "false"),
        "emergency_stop": store.setting("emergency_stop", "true"),
    }
    payload = redact(report) if redacted else report
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(payload), encoding="utf-8")
    typer.echo(str(output))


if __name__ == "__main__":
    app()

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest

from infinite_buying_dbapi.broker import AmbiguousOrderError, BrokerError, DbSecBroker
from infinite_buying_dbapi.market_calendar import session_schedule
from infinite_buying_dbapi.models import IntentRole, OrderIntent, OrderType, Phase, Side
from infinite_buying_dbapi.security import redact


def intent(order_type: OrderType = OrderType.LOC) -> OrderIntent:
    return OrderIntent(
        "i1",
        "h1",
        "c1",
        "p1",
        "pure-v4-ruleset-1",
        date(2026, 1, 5),
        Phase.BUY,
        Side.BUY,
        order_type,
        IntentRole.INITIAL_BUY,
        2,
        None if order_type == OrderType.MOC else Decimal("100.25"),
        Decimal("200.50"),
        Decimal(1),
        "test",
    )


def test_dbsec_payload_uses_official_codes() -> None:
    calls = []
    broker = DbSecBroker("https://example.test", "token", before_request=lambda: calls.append("called"))
    payload = broker.build_order_payload(intent())
    assert payload["In"]["AstkBnsTpCode"] == "2"
    assert payload["In"]["AstkOrdprcPtnCode"] == "5"
    assert payload["In"]["AstkOrdCndiTpCode"] == "1"
    assert payload["In"]["OrdTrdTpCode"] == "0"
    assert calls == []


def test_dbsec_successful_order_and_cancellation() -> None:
    seen = []

    def response(request: httpx.Request) -> httpx.Response:
        seen.append(request.read().decode("utf-8"))
        return httpx.Response(200, json={"Out": {"OrdNo": 123}, "rsp_cd": "00000", "rsp_msg": "ok"})

    broker = DbSecBroker("https://example.test", "token", client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(response)))
    placed = broker.place_order_for_symbol("TQQQ", intent())
    cancelled = broker.cancel_order_for_symbol("TQQQ", "123", intent())
    assert placed.broker_order_no == "123" and placed.status == "ACCEPTED"
    assert cancelled.status == "CANCEL_REQUESTED"
    assert all('"AstkIsuNo":"TQQQ"' in body for body in seen)
    assert '"OrdTrdTpCode":"2"' in seen[-1]


def test_dbsec_rejection_and_public_symbol_less_methods_fail() -> None:
    client = httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"rsp_cd": "99999", "rsp_msg": "no"}))
    )
    broker = DbSecBroker("https://example.test", "token", client=client)
    with pytest.raises(BrokerError, match="rejected order"):
        broker.place_order_for_symbol("TQQQ", intent())
    with pytest.raises(BrokerError, match="immutable profile symbol"):
        broker.place_order(intent())
    with pytest.raises(BrokerError, match="immutable profile symbol"):
        broker.cancel_order("1", intent())


def test_timeout_is_ambiguous_and_not_retryable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("unknown", request=request)

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(timeout))
    broker = DbSecBroker("https://example.test", "token", client=client)
    with pytest.raises(AmbiguousOrderError):
        broker.place_order_for_symbol("TQQQ", intent())


def test_orderable_amount_parses_official_fields() -> None:
    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/able-orderqty")
        return httpx.Response(200, json={"Out": {"AstkOrdAbleAmt": "1000.50", "AstkOrdAbleQty": "10.000000"}, "rsp_cd": "00000"})

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(response))
    broker = DbSecBroker("https://example.test", "token", client=client)
    amount, quantity = broker.orderable_amount("TQQQ", Side.BUY, Decimal("100"))
    assert amount == Decimal("1000.50")
    assert quantity == 10


def test_daily_chart_normalizes_and_sorts() -> None:
    def response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Out": [
                    {"Date": "20260105", "Prpr": "101", "Oprc": "100", "Hprc": "102", "Lprc": "99", "AcmlVol": "2000"},
                    {"Date": "20260102", "Prpr": "100", "Oprc": "98", "Hprc": "101", "Lprc": "97", "AcmlVol": "1000"},
                ],
                "rsp_cd": "00000",
            },
        )

    broker = DbSecBroker("https://example.test", "token", client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(response)))
    candles = broker.daily_candles("TQQQ", date(2026, 1, 1), date(2026, 1, 5))
    assert [item["date"] for item in candles] == [date(2026, 1, 2), date(2026, 1, 5)]
    assert candles[-1]["close"] == Decimal("101")


def test_current_price_and_paginated_holdings() -> None:
    calls = 0

    def response(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path.endswith("/price"):
            return httpx.Response(200, json={"Out": {"Prpr": "101.25"}, "rsp_cd": "00000"})
        calls += 1
        if calls == 1:
            return httpx.Response(200, headers={"cont_key": "NEXT"}, json={"Out2": [{"SymCode": "SOXL", "AstkExecBaseQty": "2"}], "rsp_cd": "00000"})
        assert request.headers["cont_yn"] == "Y"
        return httpx.Response(200, json={"Out2": [{"AstkIsuNo": "TQQQ.US", "AstkExecBaseQty": "3"}], "rsp_cd": "00000"})

    broker = DbSecBroker("https://example.test", "token", client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(response)))
    assert broker.current_price("TQQQ") == Decimal("101.25")
    assert broker.holding("TQQQ")["AstkExecBaseQty"] == "3"


def test_holdings_treats_official_no_records_code_as_empty() -> None:
    client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"rsp_cd": "2679", "rsp_msg": "조회내역이 없습니다"})),
    )
    assert DbSecBroker("https://example.test", "token", client=client).holdings() == []


def test_transaction_history_treats_no_records_code_as_empty() -> None:
    client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"rsp_cd": "2679", "rsp_msg": "조회내역이 없습니다"})),
    )
    broker = DbSecBroker("https://example.test", "token", client=client)
    assert broker.transaction_history(date(2026, 1, 1), date(2026, 1, 2)) == []


def test_holdings_rejects_repeated_continuation_key_and_non_object_rows() -> None:
    repeated = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={"cont_key": "SAME"}, json={"rsp_cd": "00000", "Out2": []})),
    )
    with pytest.raises(BrokerError, match="repeated a continuation key"):
        DbSecBroker("https://example.test", "token", client=repeated).holdings()

    malformed = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"rsp_cd": "00000", "Out2": ["bad"]})),
    )
    with pytest.raises(BrokerError, match="non-object row"):
        DbSecBroker("https://example.test", "token", client=malformed).holdings()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_read_only_http_errors_are_sanitized(status) -> None:
    client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={"authorization": "Bearer secret"})),
    )
    with pytest.raises(BrokerError, match=rf"HTTP {status}") as error:
        DbSecBroker("https://example.test", "token", client=client).holdings()
    assert "secret" not in str(error.value)


def test_transaction_history_builds_official_query() -> None:
    throttles = []

    def response(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        assert '"QryTpCode":"1"' in body
        assert '"AstkIsuNo":"TQQQ"' in body
        return httpx.Response(200, json={"Out": [{"OrdNo": 1}], "rsp_cd": "00000"})

    broker = DbSecBroker(
        "https://example.test",
        "token",
        client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(response)),
        before_request=lambda: throttles.append("called"),
    )
    assert broker.transaction_history(date(2026, 1, 5), date(2026, 1, 5), "TQQQ") == [{"OrdNo": 1}]
    assert throttles == ["called"]


def test_invalid_broker_responses_fail_closed() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"Out2": {}, "rsp_cd": "00000"}),
            httpx.Response(200, json={"Out": {"Prpr": "0"}, "rsp_cd": "00000"}),
            httpx.Response(200, json={"Out2": {}, "rsp_cd": "00000"}),
        ]
    )
    broker = DbSecBroker(
        "https://example.test", "token", client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(lambda request: next(responses)))
    )
    with pytest.raises(BrokerError, match="missing required"):
        broker.orderable_amount("TQQQ", Side.BUY, Decimal("100"))
    with pytest.raises(BrokerError, match="non-positive"):
        broker.current_price("TQQQ")
    with pytest.raises(BrokerError, match="Out2 is not an array"):
        broker.holdings()


def test_non_numeric_price_fails_closed_without_decimal_traceback() -> None:
    client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"Out": {"Prpr": "-"}, "rsp_cd": "00000"})),
    )
    broker = DbSecBroker("https://example.test", "token", client=client)
    with pytest.raises(BrokerError, match="missing Prpr"):
        broker.current_price("SOXL", market_code="FA")


def test_early_close_schedule_uses_exchange_calendar() -> None:
    schedule = session_schedule(date(2025, 11, 28))
    assert schedule.regular_open.hour == 9 and schedule.regular_open.minute == 30
    assert schedule.regular_close.hour == 13
    assert schedule.loc_cutoff.hour == 12 and schedule.loc_cutoff.minute == 50
    assert schedule.premarket_open.hour == 4


def test_non_session_rejected() -> None:
    with pytest.raises(ValueError):
        session_schedule(date(2026, 1, 3))


def test_diagnostics_redaction() -> None:
    value = {"access_token": "secret", "nested": {"account_number": "12345678"}, "safe": "TQQQ"}
    redacted = redact(value)
    assert redacted["access_token"] == "***REDACTED***"
    assert redacted["nested"]["account_number"] == "***REDACTED***"
    assert redacted["safe"] == "TQQQ"

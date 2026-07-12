from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Protocol

import httpx

from .models import BrokerOrder, OrderIntent, OrderType, Side, canonical_json


class BrokerError(RuntimeError):
    pass


class AmbiguousOrderError(BrokerError):
    """The request may have reached the broker; callers must reconcile."""


class Broker(Protocol):
    def place_order(self, intent: OrderIntent) -> BrokerOrder: ...
    def cancel_order(self, broker_order_no: str, intent: OrderIntent) -> BrokerOrder: ...


class PreviewBroker:
    def place_order(self, intent: OrderIntent) -> BrokerOrder:
        return BrokerOrder(
            broker_order_no=f"PREVIEW-{intent.intent_id[:12]}",
            intent_id=intent.intent_id,
            status="PREVIEW",
            requested_qty=intent.quantity,
            remaining_qty=intent.quantity,
            raw_response_hash="preview",
        )

    def cancel_order(self, broker_order_no: str, intent: OrderIntent) -> BrokerOrder:
        return BrokerOrder(
            broker_order_no=broker_order_no,
            intent_id=intent.intent_id,
            status="CANCELLED",
            requested_qty=intent.quantity,
            remaining_qty=0,
            raw_response_hash="preview-cancel",
        )


class PaperBroker:
    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def place_order(self, intent: OrderIntent) -> BrokerOrder:
        return BrokerOrder(
            broker_order_no=f"PAPER-{next(self._counter):08d}",
            intent_id=intent.intent_id,
            status="ACCEPTED",
            requested_qty=intent.quantity,
            remaining_qty=intent.quantity,
            raw_response_hash=sha256(intent.intent_id.encode()).hexdigest(),
        )

    def cancel_order(self, broker_order_no: str, intent: OrderIntent) -> BrokerOrder:
        return BrokerOrder(
            broker_order_no=broker_order_no,
            intent_id=intent.intent_id,
            status="CANCELLED",
            requested_qty=intent.quantity,
            remaining_qty=0,
            raw_response_hash="paper-cancel",
        )


class DbSecBroker:
    ORDER_PATH = "/api/v1/trading/overseas-stock/order"
    TRANSACTION_PATH = "/api/v1/trading/overseas-stock/inquiry/transaction-history"
    BALANCE_PATH = "/api/v1/trading/overseas-stock/inquiry/balance-margin"
    ORDERABLE_PATH = "/api/v1/trading/overseas-stock/inquiry/able-orderqty"
    CURRENT_PRICE_PATH = "/api/v1/quote/overseas-stock/inquiry/price"
    DAILY_CHART_PATH = "/api/v1/quote/overseas-stock/chart/day"

    ORDER_TYPE_CODES = {OrderType.LIMIT: "1", OrderType.LOC: "5", OrderType.MOC: "6"}
    SIDE_CODES = {Side.SELL: "1", Side.BUY: "2"}

    def __init__(
        self,
        base_url: str,
        access_token: str,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
        before_request: Callable[[], None] | None = None,
    ):
        if not access_token:
            raise ValueError("access token is required")
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout_seconds)
        self.access_token = access_token
        self.before_request = before_request or (lambda: None)

    def _headers(self, *, continuation: bool = False, continuation_key: str = "") -> dict[str, str]:
        token = self.access_token if self.access_token.lower().startswith("bearer ") else f"Bearer {self.access_token}"
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": token,
            "cont_yn": "Y" if continuation else "N",
            "cont_key": continuation_key,
        }

    def place_order(self, intent: OrderIntent) -> BrokerOrder:
        raise BrokerError("DB Securities orders require an immutable profile symbol; use place_order_for_symbol")

    def cancel_order(self, broker_order_no: str, intent: OrderIntent) -> BrokerOrder:
        raise BrokerError("DB Securities cancellations require an immutable profile symbol; use cancel_order_for_symbol")

    def cancel_order_for_symbol(self, symbol: str, broker_order_no: str, intent: OrderIntent) -> BrokerOrder:
        payload = self.build_order_payload(intent, trade_code="2", original_order_no=broker_order_no)
        payload["In"]["AstkIsuNo"] = symbol
        response = self._post_order(payload)
        if response.get("rsp_cd") != "00000":
            raise BrokerError(f"DB Securities rejected cancellation: {response.get('rsp_cd')} {response.get('rsp_msg', '')}")
        return BrokerOrder(
            broker_order_no=broker_order_no,
            intent_id=intent.intent_id,
            status="CANCEL_REQUESTED",
            requested_qty=intent.quantity,
            remaining_qty=intent.quantity,
            raw_response_hash=sha256(canonical_json(response).encode()).hexdigest(),
        )

    def transaction_history(
        self,
        start: date,
        end: date,
        symbol: str = "",
        side_code: str = "0",
        execution_code: str = "0",
    ) -> list[dict[str, Any]]:
        body = {
            "In": {
                "QrySrtDt": start.strftime("%Y%m%d"),
                "QryEndDt": end.strftime("%Y%m%d"),
                "AstkIsuNo": symbol,
                "AstkBnsTpCode": side_code,
                "OrdxctTpCode": execution_code,
                "StnlnTpCode": "1",
                "QryTpCode": "1",
                "OnlineYn": "0",
                "CvrgOrdYn": "0",
                "WonFcurrTpCode": "2",
            }
        }
        return self._all_pages(self.TRANSACTION_PATH, body, "Out")

    def holdings(self) -> list[dict[str, Any]]:
        body = {"In": {"WonFcurrTpCode": "2", "TrxTpCode": "2", "CmsnTpCode": "2", "DpntBalTpCode": "1"}}
        return self._all_pages(self.BALANCE_PATH, body, "Out2")

    def holding(self, symbol: str) -> dict[str, Any] | None:
        wanted = symbol.upper()
        for row in self.holdings():
            if str(row.get("SymCode", "")).upper() == wanted or str(row.get("AstkIsuNo", "")).upper().split(".")[0] == wanted:
                return row
        return None

    def _all_pages(self, path: str, body: dict[str, Any], array_key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        continuation_key = ""
        seen_keys: set[str] = set()
        while True:
            response, next_key = self.raw_inquiry(path, body, continuation_key=continuation_key)
            if response.get("rsp_cd") != "00000":
                raise BrokerError(f"DB Securities inquiry rejected: {response.get('rsp_cd')} {response.get('rsp_msg', '')}")
            page = response.get(array_key)
            if page is None:
                page = []
            if not isinstance(page, list):
                raise BrokerError(f"DB Securities {array_key} is not an array")
            rows.extend(item for item in page if isinstance(item, dict))
            if not next_key:
                return rows
            if next_key in seen_keys:
                raise BrokerError("DB Securities repeated a continuation key")
            seen_keys.add(next_key)
            continuation_key = next_key

    def build_order_payload(self, intent: OrderIntent, trade_code: str = "0", original_order_no: str = "0") -> dict[str, Any]:
        return {
            "In": {
                "AstkIsuNo": "",  # populated by execution from the immutable profile
                "AstkBnsTpCode": self.SIDE_CODES[intent.side],
                "AstkOrdprcPtnCode": self.ORDER_TYPE_CODES[intent.order_type],
                "AstkOrdCndiTpCode": "1",
                "AstkOrdQty": intent.quantity,
                "AstkOrdPrc": float(intent.limit_price) if intent.limit_price is not None else 0,
                "OrdTrdTpCode": trade_code,
                "OrgOrdNo": int(original_order_no),
            }
        }

    def place_order_for_symbol(self, symbol: str, intent: OrderIntent) -> BrokerOrder:
        payload = self.build_order_payload(intent)
        payload["In"]["AstkIsuNo"] = symbol
        response = self._post_order(payload)
        out = response.get("Out") or {}
        if response.get("rsp_cd") != "00000" or not out.get("OrdNo"):
            raise BrokerError(f"DB Securities rejected order: {response.get('rsp_cd')} {response.get('rsp_msg', '')}")
        return BrokerOrder(
            broker_order_no=str(out["OrdNo"]),
            intent_id=intent.intent_id,
            status="ACCEPTED",
            requested_qty=intent.quantity,
            remaining_qty=intent.quantity,
            raw_response_hash=sha256(canonical_json(response).encode()).hexdigest(),
        )

    def raw_inquiry(self, path: str, body: dict[str, Any], *, continuation_key: str = "") -> tuple[dict[str, Any], str]:
        try:
            self.before_request()
            response = self.client.post(path, headers=self._headers(continuation=bool(continuation_key), continuation_key=continuation_key), json=body)
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise BrokerError(f"DB Securities inquiry failed: {exc.__class__.__name__}") from exc
        return response.json(), response.headers.get("cont_key", "")

    def orderable_amount(self, symbol: str, side: Side, price: Decimal, currency_code: str = "2") -> tuple[Decimal, int]:
        if currency_code not in {"1", "2"}:
            raise ValueError("currency_code must be 1 (KRW) or 2 (foreign currency)")
        payload = {
            "In": {
                "TrxTpCode": self.SIDE_CODES[side],
                "AstkIsuNo": symbol,
                "AstkOrdPrc": float(price),
                "WonFcurrTpCode": currency_code,
            }
        }
        response, _ = self.raw_inquiry(self.ORDERABLE_PATH, payload)
        if response.get("rsp_cd") != "00000":
            raise BrokerError(f"DB Securities orderable inquiry failed: {response.get('rsp_cd')} {response.get('rsp_msg', '')}")
        out = response.get("Out") or {}
        try:
            return Decimal(str(out["AstkOrdAbleAmt"])), int(Decimal(str(out["AstkOrdAbleQty"])))
        except (KeyError, ValueError, TypeError) as exc:
            raise BrokerError("DB Securities orderable response is missing required fields") from exc

    def current_price(self, symbol: str, market_code: str = "FN") -> Decimal:
        response, _ = self.raw_inquiry(
            self.CURRENT_PRICE_PATH,
            {"In": {"InputCondMrktDivCode": market_code, "InputIscd1": symbol}},
        )
        if response.get("rsp_cd") != "00000":
            raise BrokerError(f"DB Securities price inquiry failed: {response.get('rsp_cd')} {response.get('rsp_msg', '')}")
        try:
            price = Decimal(str((response.get("Out") or {})["Prpr"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise BrokerError("DB Securities price response is missing Prpr") from exc
        if price <= 0:
            raise BrokerError("DB Securities returned a non-positive current price")
        return price

    def daily_candles(self, symbol: str, start: date, end: date, market_code: str = "FN") -> list[dict[str, Any]]:
        body = {
            "In": {
                "InputOrgAdjPrc": "1",
                "InputCondMrktDivCode": market_code,
                "InputIscd1": symbol,
                "InputDate1": start.strftime("%Y%m%d"),
                "InputDate2": end.strftime("%Y%m%d"),
            }
        }
        rows = self._all_pages(self.DAILY_CHART_PATH, body, "Out")
        normalized: list[dict[str, Any]] = []
        for row in rows:
            try:
                normalized.append(
                    {
                        "date": datetime.strptime(str(row["Date"]), "%Y%m%d").date(),
                        "close": Decimal(str(row["Prpr"])),
                        "open": Decimal(str(row["Oprc"])),
                        "high": Decimal(str(row["Hprc"])),
                        "low": Decimal(str(row["Lprc"])),
                        "volume": int(Decimal(str(row["AcmlVol"]))),
                    }
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise BrokerError("DB Securities daily chart row is malformed") from exc
        return sorted(normalized, key=lambda item: item["date"])

    def _post_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            self.before_request()
            response = self.client.post(self.ORDER_PATH, headers=self._headers(), json=payload)
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AmbiguousOrderError("order result is unknown; reconcile before any retry") from exc
        except httpx.HTTPStatusError as exc:
            raise BrokerError(f"DB Securities HTTP error: {exc.response.status_code}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise AmbiguousOrderError("order response was not valid JSON; reconcile before any retry") from exc

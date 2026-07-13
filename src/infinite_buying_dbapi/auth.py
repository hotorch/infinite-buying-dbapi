from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from .security import get_secret, store_secret
from .store import StateStore


class OAuthError(RuntimeError):
    pass


class DbSecTokenManager:
    TOKEN_PATH = "/oauth2/token"
    REVOKE_PATH = "/oauth2/revoke"

    def __init__(
        self,
        base_url: str,
        account_alias: str,
        store: StateStore,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
        oauth_style: str = "form",
    ):
        if oauth_style not in {"json", "form"}:
            raise ValueError("oauth_style must be json or form")
        self.account_alias = account_alias
        self.store = store
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout_seconds)
        self.oauth_style = oauth_style

    def access_token(self) -> str:
        cached = get_secret(self.account_alias, "access_token")
        expires_at = get_secret(self.account_alias, "access_token_expires_at")
        if cached and expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at)
            except ValueError:
                expiry = datetime.min.replace(tzinfo=timezone.utc)
            if expiry > datetime.now(timezone.utc) + timedelta(minutes=5):
                return cached
        return self.issue()

    def issue(self) -> str:
        self._check_credential_expiry()
        app_key, app_secret = self._credentials()
        now = datetime.now(timezone.utc)
        if not self.store.claim_oauth_request(self.account_alias, now, 60):
            previous = self.store.setting(f"oauth_last_request_at:{self.account_alias}")
            retry_at = datetime.fromisoformat(previous) + timedelta(seconds=60) if previous else now + timedelta(seconds=60)
            raise OAuthError(f"DB Securities token issuance is limited to one request per minute; retry after {retry_at.isoformat()}")
        if self.oauth_style == "json":
            response = self.client.post(
                self.TOKEN_PATH,
                headers={"content-type": "application/json"},
                json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
            )
        else:
            response = self.client.post(
                self.TOKEN_PATH,
                headers={"content-type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials", "appkey": app_key, "appsecretkey": app_secret, "scope": "oob"},
            )
        try:
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            retry_at = now + timedelta(seconds=60)
            raise OAuthError(f"DB Securities token issuance failed with HTTP {status}; retry after {retry_at.isoformat()}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            retry_at = now + timedelta(seconds=60)
            raise OAuthError(f"DB Securities token issuance failed; retry after {retry_at.isoformat()}") from exc
        token = payload.get("access_token") or payload.get("token")
        expires_in = payload.get("expires_in") or payload.get("expire_in")
        if not token or not expires_in:
            raise OAuthError("DB Securities token response is missing token or expiry")
        expiry = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        store_secret(self.account_alias, "access_token", str(token))
        store_secret(self.account_alias, "access_token_expires_at", expiry.isoformat())
        return str(token)

    def revoke(self) -> None:
        app_key, app_secret = self._credentials()
        token = get_secret(self.account_alias, "access_token")
        if not token:
            return
        response = self.client.post(
            self.REVOKE_PATH,
            headers={"content-type": "application/x-www-form-urlencoded"},
            data={"appkey": app_key, "appsecretkey": app_secret, "token_type_hint": "access_token", "token": token},
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthError("DB Securities token revocation failed") from exc
        if str(payload.get("code")) != "200":
            raise OAuthError("DB Securities rejected token revocation")
        store_secret(self.account_alias, "access_token", "REVOKED")
        store_secret(self.account_alias, "access_token_expires_at", datetime.min.replace(tzinfo=timezone.utc).isoformat())

    def _credentials(self) -> tuple[str, str]:
        app_key = get_secret(self.account_alias, "app_key")
        app_secret = get_secret(self.account_alias, "app_secret")
        if not app_key or not app_secret:
            raise OAuthError("DB Securities app key and app secret are not configured")
        return app_key, app_secret

    def _check_credential_expiry(self) -> None:
        raw = self.store.setting("dbsec_credential_expire_date")
        if raw and date.fromisoformat(raw) < datetime.now(timezone.utc).date():
            raise OAuthError("DB Securities app credentials have expired; renew APP KEY and APP SECRET before retrying")

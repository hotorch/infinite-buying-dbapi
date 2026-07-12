from __future__ import annotations

import httpx
import pytest

import infinite_buying_dbapi.auth as auth_module
from infinite_buying_dbapi.auth import DbSecTokenManager, OAuthError
from infinite_buying_dbapi.store import StateStore


def test_oauth_issue_cache_and_revoke(tmp_path, monkeypatch) -> None:
    secrets = {"a:app_key": "key", "a:app_secret": "secret"}
    monkeypatch.setattr(auth_module, "get_secret", lambda alias, name: secrets.get(f"{alias}:{name}"))
    monkeypatch.setattr(auth_module, "store_secret", lambda alias, name, value: secrets.__setitem__(f"{alias}:{name}", value))
    calls = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/token"):
            assert b"grant_type=client_credentials" in request.read()
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 86400})
        return httpx.Response(200, json={"code": 200, "message": "ok"})

    store = StateStore(tmp_path / "state.sqlite3")
    manager = DbSecTokenManager(
        "https://example.test",
        "a",
        store,
        client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(response)),
        oauth_style="form",
    )
    assert manager.access_token() == "token-1"
    assert manager.access_token() == "token-1"
    assert calls == ["/oauth2/token"]
    manager.revoke()
    assert calls[-1] == "/oauth2/revoke"
    assert secrets["a:access_token"] == "REVOKED"


def test_oauth_json_style_matches_public_howto_page(tmp_path, monkeypatch) -> None:
    secrets = {"a:app_key": "key", "a:app_secret": "secret"}
    monkeypatch.setattr(auth_module, "get_secret", lambda alias, name: secrets.get(f"{alias}:{name}"))
    monkeypatch.setattr(auth_module, "store_secret", lambda alias, name, value: secrets.__setitem__(f"{alias}:{name}", value))

    def response(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"] == "application/json"
        body = request.read()
        assert b'"appsecret":"secret"' in body
        assert b"appsecretkey" not in body
        return httpx.Response(200, json={"access_token": "token-json", "expires_in": 86400})

    manager = DbSecTokenManager(
        "https://example.test",
        "a",
        StateStore(tmp_path / "state.sqlite3"),
        client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(response)),
    )
    assert manager.issue() == "token-json"


def test_oauth_rate_limit_and_missing_credentials(tmp_path, monkeypatch) -> None:
    secrets = {"a:app_key": "key", "a:app_secret": "secret"}
    monkeypatch.setattr(auth_module, "get_secret", lambda alias, name: secrets.get(f"{alias}:{name}"))
    monkeypatch.setattr(auth_module, "store_secret", lambda alias, name, value: secrets.__setitem__(f"{alias}:{name}", value))
    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
    store = StateStore(tmp_path / "state.sqlite3")
    manager = DbSecTokenManager("https://example.test", "a", store, client=client)
    with pytest.raises(OAuthError, match="missing token"):
        manager.issue()
    with pytest.raises(OAuthError, match="one request per minute"):
        manager.issue()

    secrets.clear()
    other = DbSecTokenManager("https://example.test", "b", store, client=client)
    with pytest.raises(OAuthError, match="not configured"):
        other.issue()

from __future__ import annotations

from app.core.config import settings
from app.core.ratelimit import reset_rate_limits
from tests.conftest import upload_sample


async def test_per_user_api_keys_isolate_tenants(client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "api_keys",
        "alice@example.com=alice-key,bob@example.com=bob-key",
    )
    monkeypatch.setattr(settings, "api_key", None)

    unauthorized = await client.get("/v1/resumes")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "unauthorized"

    alice_headers = {"X-API-Key": "alice-key"}
    alice = await upload_sample(client, headers=alice_headers)
    alice_list = await client.get("/v1/resumes", headers=alice_headers)
    assert alice_list.status_code == 200
    assert alice_list.json()["total"] == 1

    bob_list = await client.get("/v1/resumes", headers={"X-API-Key": "bob-key"})
    assert bob_list.status_code == 200
    assert bob_list.json()["total"] == 0
    assert (
        await client.get(f"/v1/resumes/{alice['id']}", headers={"X-API-Key": "bob-key"})
    ).status_code == 404

    query_key = await client.get("/v1/resumes?api_key=alice-key")
    assert query_key.status_code == 200
    assert query_key.json()["total"] == 1


async def test_request_rate_limit_returns_429(client, monkeypatch):
    reset_rate_limits()
    monkeypatch.setattr(settings, "rate_limit_requests_per_minute", 1)

    first = await client.get("/v1/resumes")
    assert first.status_code == 200

    second = await client.get("/v1/resumes")
    assert second.status_code == 429
    body = second.json()
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["details"]["retry_after"] >= 1
    reset_rate_limits()

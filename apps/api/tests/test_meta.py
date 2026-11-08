from __future__ import annotations


async def test_health(client):
    response = await client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert response.headers["x-request-id"]


async def test_meta_documents_weights(client):
    response = await client.get("/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert abs(sum(body["scoring_weights"].values()) - 1.0) < 1e-9
    assert body["scoring_weights"]["keyword_match"] == 0.30
    assert body["caps"]["missing_must_have"] == 70.0


async def test_api_key_required_when_configured(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_key", "secret-key")
    response = await client.get("/v1/facts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

    allowed = await client.get("/v1/facts", headers={"X-API-Key": "secret-key"})
    assert allowed.status_code == 200

    query_key = await client.get("/v1/facts?api_key=secret-key")
    assert query_key.status_code == 200

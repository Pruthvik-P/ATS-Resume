from __future__ import annotations


async def test_facts_bank_crud(client):
    created = await client.post(
        "/v1/facts",
        json={
            "fact_text": "Scaled the payments service from 10k to 2M requests/day.",
            "source": "user",
            "tags": ["scale", "payments"],
        },
    )
    assert created.status_code == 201, created.text
    fact = created.json()
    assert fact["tags"] == ["scale", "payments"]
    assert fact["confirmed_at"]

    listing = await client.get("/v1/facts")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    deleted = await client.delete(f"/v1/facts/{fact['id']}")
    assert deleted.status_code == 204

    listing = await client.get("/v1/facts")
    assert listing.json()["total"] == 0


async def test_fact_validation(client):
    response = await client.post("/v1/facts", json={"fact_text": "x"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

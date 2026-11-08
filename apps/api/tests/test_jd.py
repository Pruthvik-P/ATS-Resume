from __future__ import annotations

from tests.conftest import create_sample_jd


async def test_jd_analysis_extracts_requirements(client):
    body = await create_sample_jd(client)
    analysis = body["analysis"]

    must = {item["canonical"] for item in analysis["must_have"]}
    nice = {item["canonical"] for item in analysis["nice_to_have"]}
    assert {"Python", "FastAPI", "PostgreSQL", "Kubernetes", "Terraform", "AWS"} <= must
    assert {"Go", "GraphQL"} <= nice
    assert analysis["must_have"] and all(item["weight"] == 2.0 for item in analysis["must_have"])
    assert analysis["nice_to_have"] and all(item["weight"] == 1.0 for item in analysis["nice_to_have"])

    assert analysis["years_min"] == 5
    assert analysis["seniority"] == "senior"
    assert analysis["title"] == "Senior Backend Engineer"
    assert any(item["kind"] == "work_authorization" for item in analysis["knockouts"])
    assert len(analysis["responsibilities"]) >= 2
    assert analysis["analyser_version"] == "deterministic-jd-v1"


async def test_jd_requires_text_or_url(client):
    response = await client.post("/v1/jds", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "jd_missing"


async def test_jd_rejects_both_text_and_url(client):
    response = await client.post(
        "/v1/jds", json={"text": "Some job text", "url": "https://example.com/job"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "jd_ambiguous"


async def test_jd_url_blocks_private_hosts(client):
    response = await client.post("/v1/jds", json={"url": "http://127.0.0.1:8000/admin"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "jd_url_blocked"


async def test_jd_get_by_id(client):
    created = await create_sample_jd(client)
    fetched = await client.get(f"/v1/jds/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["analysis"]["title"] == "Senior Backend Engineer"

    listing = await client.get("/v1/jds")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

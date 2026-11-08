from __future__ import annotations

from tests.conftest import create_sample_jd, upload_sample


async def test_score_report_is_explainable_and_capped(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)

    response = await client.post(
        "/v1/score", json={"resume_id": resume["id"], "jd_id": jd["id"]}
    )
    assert response.status_code == 201, response.text
    report = response.json()

    assert report["id"]
    assert 0 <= report["overall_score"] <= 100
    assert report["raw_score"] >= report["overall_score"]
    assert report["grade"]

    keyword = report["breakdown"]["keyword_match"]
    assert "Terraform" in keyword["missing_must_have"]
    assert "Python" in keyword["matched"]
    # Skills-list-only matches are discounted, not treated as full evidence.
    kubernetes = next(item for item in keyword["evidence"] if item["skill"] == "Kubernetes")
    assert kubernetes["location"] == "skills_list"
    assert kubernetes["credit"] < 1.0

    assert report["caps"], "missing must-have skills should cap the score"
    assert any(cap["code"] == "missing_must_have" for cap in report["caps"])
    assert report["overall_score"] <= 70.0

    assert report["breakdown"]["experience_fit"]["total_years"] >= 5
    assert report["breakdown"]["parseability"]["field_recall"] > 80
    assert report["weights"]["keyword_match"] == 0.30
    assert report["model_versions"]["embedding"] == "hashed-ngram-v1"

    types = {item["type"] for item in report["recommendations"]}
    assert "missing_skill" in types
    assert any(item["priority"] == "high" for item in report["recommendations"])


async def test_score_can_be_retrieved_and_listed(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    created = (
        await client.post("/v1/score", json={"resume_id": resume["id"], "jd_id": jd["id"]})
    ).json()

    fetched = await client.get(f"/v1/scores/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["overall_score"] == created["overall_score"]

    listing = await client.get(f"/v1/resumes/{resume['id']}/scores")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


async def test_score_is_deterministic(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    payload = {"resume_id": resume["id"], "jd_id": jd["id"]}
    first = (await client.post("/v1/score", json=payload)).json()
    second = (await client.post("/v1/score", json=payload)).json()

    assert first["overall_score"] == second["overall_score"]
    assert first["raw_score"] == second["raw_score"]
    assert first["breakdown"]["keyword_match"]["score"] == second["breakdown"]["keyword_match"]["score"]


async def test_score_missing_resume_returns_404(client):
    jd = await create_sample_jd(client)
    response = await client.post(
        "/v1/score",
        json={"resume_id": "00000000-0000-0000-0000-000000000000", "jd_id": jd["id"]},
    )
    assert response.status_code == 404

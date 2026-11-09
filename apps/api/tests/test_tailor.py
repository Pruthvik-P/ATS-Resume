from __future__ import annotations

from app.core.config import settings
from tests.conftest import create_sample_jd, upload_sample


async def _second_jd(client) -> dict:
    response = await client.post(
        "/v1/jds",
        json={
            "text": (
                "Go Backend Engineer\n\nRequirements\n"
                "- Go required\n- GraphQL preferred\n- 3+ years of experience"
            ),
            "title": "Go Backend Engineer",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_multi_jd_tailor_preview_compares_targets(client):
    resume = await upload_sample(client)
    first = await create_sample_jd(client)
    second = await _second_jd(client)

    response = await client.post(
        f"/v1/resumes/{resume['id']}/tailor",
        json={
            "jd_ids": [first["id"], second["id"]],
            "options": {"max_iterations": 1, "max_changes": 8},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resume_id"] == resume["id"]
    assert len(body["targets"]) == 2
    assert {target["jd_id"] for target in body["targets"]} == {
        first["id"],
        second["id"],
    }
    for target in body["targets"]:
        assert 0 <= target["baseline_score"] <= 100
        assert 0 <= target["proposed_score"] <= 100
        assert target["proposal_count"] >= target["verified_count"]
    assert "preview" in body["note"].lower()


async def test_multi_jd_tailor_respects_target_limit(client, monkeypatch):
    resume = await upload_sample(client)
    first = await create_sample_jd(client)
    second = await _second_jd(client)
    monkeypatch.setattr(settings, "multi_jd_max_targets", 1)

    response = await client.post(
        f"/v1/resumes/{resume['id']}/tailor",
        json={"jd_ids": [first["id"], second["id"]]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "too_many_targets"


async def test_multi_jd_tailor_rejects_unknown_jd(client):
    resume = await upload_sample(client)
    response = await client.post(
        f"/v1/resumes/{resume['id']}/tailor",
        json={"jd_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert response.status_code == 404

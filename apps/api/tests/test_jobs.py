from __future__ import annotations

from tests.conftest import create_sample_jd, upload_sample


async def test_optimise_job_produces_verified_proposals(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)

    queued = await client.post(
        "/v1/optimise",
        json={
            "resume_id": resume["id"],
            "jd_id": jd["id"],
            "options": {"max_iterations": 2, "suggest_metrics": True},
        },
    )
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["id"]

    job = (await client.get(f"/v1/jobs/{job_id}")).json()
    assert job["status"] == "succeeded", job
    assert job["progress"] == 100
    result = job["result"]
    assert result["baseline_score"] <= 70.0
    assert result["proposals"]

    kinds = {proposal["kind"] for proposal in result["proposals"]}
    assert "rewrite_bullet" in kinds or "reorder_skills" in kinds
    assert "parse_fix" in kinds

    rewrite = next(
        (proposal for proposal in result["proposals"] if proposal["kind"] == "rewrite_bullet"),
        None,
    )
    if rewrite is not None:
        assert rewrite["truthfulness"] == "verified"
        assert rewrite["proposed"] != rewrite["original"]

    metric = next(
        (proposal for proposal in result["proposals"] if proposal["kind"] == "placeholder_metric"),
        None,
    )
    if metric is not None:
        assert metric["truthfulness"] == "needs_user_input"
        assert "[ADD METRIC" in metric["proposed"]

    missing = next(
        (
            proposal
            for proposal in result["proposals"]
            if proposal["kind"] == "missing_skill_question"
        ),
        None,
    )
    assert missing is not None
    assert "Terraform" in missing["rationale"]
    assert missing["proposed"] == ""


async def test_accept_change_recomputes_score(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    queued = await client.post(
        "/v1/optimise", json={"resume_id": resume["id"], "jd_id": jd["id"]}
    )
    job_id = queued.json()["id"]
    result = (await client.get(f"/v1/jobs/{job_id}")).json()["result"]

    verified = [
        proposal
        for proposal in result["proposals"]
        if proposal["truthfulness"] == "verified"
    ]
    assert verified
    change = verified[0]

    decision = await client.post(
        f"/v1/jobs/{job_id}/changes/{change['id']}", json={"status": "accepted"}
    )
    assert decision.status_code == 200, decision.text
    body = decision.json()
    assert body["change"]["status"] == "accepted"
    assert 0 <= body["score_after_accepted"] <= 100

    refreshed = (await client.get(f"/v1/jobs/{job_id}")).json()["result"]
    accepted = [item for item in refreshed["proposals"] if item["status"] == "accepted"]
    assert len(accepted) == 1


async def test_unknown_job_returns_404(client):
    response = await client.get("/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404

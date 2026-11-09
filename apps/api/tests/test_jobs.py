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
    assert result["model_versions"]["scoring"] == "scoring-v2"
    assert "taxonomy" in result["model_versions"]
    assert result["model_versions"]["fairness"] == "redaction-v1"

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

    versions_response = await client.get(f"/v1/resumes/{resume['id']}/versions")
    assert versions_response.status_code == 200, versions_response.text
    versions = versions_response.json()
    assert len(versions) == 2
    latest = versions[0]
    assert latest["version"] == 2
    assert latest["score_id"] is not None
    assert any(
        entry.get("job_id") == job_id and entry.get("status") == "accepted"
        for entry in latest["change_log"]
    )

    scores = (await client.get(f"/v1/resumes/{resume['id']}/scores")).json()
    assert len(scores) == 1
    assert scores[0]["id"] == latest["score_id"]


async def test_edit_metric_placeholder_records_fact_and_snapshot(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    queued = await client.post(
        "/v1/optimise",
        json={
            "resume_id": resume["id"],
            "jd_id": jd["id"],
            "options": {"suggest_metrics": True},
        },
    )
    job_id = queued.json()["id"]
    result = (await client.get(f"/v1/jobs/{job_id}")).json()["result"]
    metric = next(
        (item for item in result["proposals"] if item["kind"] == "placeholder_metric"),
        None,
    )
    assert metric is not None
    assert "[ADD METRIC" in metric["proposed"]
    # The full source bullet is retained so the editor can show a real diff.
    assert metric["original"]
    assert metric["original"] != metric["proposed"]

    edited = metric["proposed"].split(" [ADD METRIC")[0] + " Reduced p95 latency by 35%."
    patched = await client.patch(
        f"/v1/jobs/{job_id}/changes/{metric['id']}",
        json={"proposed": edited},
    )
    assert patched.status_code == 200, patched.text
    change = patched.json()
    assert change["proposed"] == edited
    assert change["edited_by_user"] is True
    assert change["truthfulness"] == "verified"

    facts = (await client.get("/v1/facts")).json()
    assert any(fact["fact_text"] == edited for fact in facts["items"])

    accepted = await client.post(
        f"/v1/jobs/{job_id}/changes/{metric['id']}", json={"status": "accepted"}
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["version_id"]
    assert body["score_id"]
    assert body["snapshot_url"]

    document = (await client.get(f"/v1/resumes/{resume['id']}")).json()["document"]
    highlights = [
        highlight
        for work in document["canonical"]["work"]
        for highlight in work["highlights"]
    ]
    assert edited in highlights

    versions = (await client.get(f"/v1/resumes/{resume['id']}/versions")).json()
    latest = versions[0]
    assert latest["snapshot_url"]
    assert latest["tex_url"]
    events = [
        entry
        for entry in latest["change_log"]
        if entry.get("type") == "change_decision"
    ]
    assert events[-1]["status"] == "accepted"
    assert events[-1]["edited_by_user"] is True
    assert any(entry.get("type") == "version_snapshot" for entry in latest["change_log"])


async def test_reject_after_accept_reverts_and_keeps_history(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    queued = await client.post(
        "/v1/optimise", json={"resume_id": resume["id"], "jd_id": jd["id"]}
    )
    job_id = queued.json()["id"]
    result = (await client.get(f"/v1/jobs/{job_id}")).json()["result"]
    change = next(
        item
        for item in result["proposals"]
        if item["truthfulness"] == "verified" and item["kind"] == "rewrite_bullet"
    )

    accepted = await client.post(
        f"/v1/jobs/{job_id}/changes/{change['id']}", json={"status": "accepted"}
    )
    assert accepted.status_code == 200, accepted.text

    rejected = await client.post(
        f"/v1/jobs/{job_id}/changes/{change['id']}", json={"status": "rejected"}
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["previous_status"] == "accepted"

    document = (await client.get(f"/v1/resumes/{resume['id']}")).json()["document"]
    highlights = [
        highlight
        for work in document["canonical"]["work"]
        for highlight in work["highlights"]
    ]
    assert change["original"] in highlights

    versions = (await client.get(f"/v1/resumes/{resume['id']}/versions")).json()
    latest = versions[0]
    events = [
        entry
        for entry in latest["change_log"]
        if entry.get("type") == "change_decision"
    ]
    assert [entry["status"] for entry in events] == ["accepted", "rejected"]
    assert events[-1]["reverted"] is True
    assert latest["snapshot_url"]


async def test_repeated_decision_is_idempotent(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    queued = await client.post(
        "/v1/optimise", json={"resume_id": resume["id"], "jd_id": jd["id"]}
    )
    job_id = queued.json()["id"]
    result = (await client.get(f"/v1/jobs/{job_id}")).json()["result"]
    change = next(
        item for item in result["proposals"] if item["truthfulness"] == "verified"
    )

    first = await client.post(
        f"/v1/jobs/{job_id}/changes/{change['id']}", json={"status": "accepted"}
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/v1/jobs/{job_id}/changes/{change['id']}", json={"status": "accepted"}
    )
    assert second.status_code == 200, second.text
    assert second.json()["idempotent_replay"] is True

    versions = (await client.get(f"/v1/resumes/{resume['id']}/versions")).json()
    events = [
        entry
        for entry in versions[0]["change_log"]
        if entry.get("type") == "change_decision"
    ]
    assert len(events) == 1


async def test_optimise_idempotency_key_replays_and_rejects_reuse(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    payload = {"resume_id": resume["id"], "jd_id": jd["id"]}

    first = await client.post(
        "/v1/optimise", json=payload, headers={"Idempotency-Key": "scan-1"}
    )
    assert first.status_code == 202, first.text
    second = await client.post(
        "/v1/optimise", json=payload, headers={"Idempotency-Key": "scan-1"}
    )
    assert second.status_code == 202, second.text
    assert second.json()["id"] == first.json()["id"]

    other_resume = await upload_sample(client)
    conflict = await client.post(
        "/v1/optimise",
        json={"resume_id": other_resume["id"], "jd_id": jd["id"]},
        headers={"Idempotency-Key": "scan-1"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_reuse"


async def test_unknown_job_returns_404(client):
    response = await client.get("/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404

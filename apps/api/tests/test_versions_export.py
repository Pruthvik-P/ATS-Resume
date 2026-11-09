from __future__ import annotations

from tests.conftest import create_sample_jd, upload_sample


async def _accepted_change(client) -> tuple[dict, dict, dict, dict]:
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    queued = await client.post(
        "/v1/optimise", json={"resume_id": resume["id"], "jd_id": jd["id"]}
    )
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["id"]
    result = (await client.get(f"/v1/jobs/{job_id}")).json()["result"]
    change = next(
        item
        for item in result["proposals"]
        if item["truthfulness"] == "verified" and item["kind"] == "rewrite_bullet"
    )
    decision = await client.post(
        f"/v1/jobs/{job_id}/changes/{change['id']}", json={"status": "accepted"}
    )
    assert decision.status_code == 200, decision.text
    return resume, jd, change, decision.json()


async def test_version_detail_diff_and_exports(client):
    resume, _jd, change, _decision = await _accepted_change(client)
    versions = (await client.get(f"/v1/resumes/{resume['id']}/versions")).json()
    assert len(versions) == 2
    latest, previous = versions[0], versions[1]

    detail = await client.get(f"/v1/versions/{latest['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["version"] == 2
    assert body["document"]["canonical"]["basics"]["name"] == "Jane Doe"
    assert incoming_original(change) not in str(body["document"]["canonical"])

    diff = await client.get(
        f"/v1/versions/{latest['id']}/diff?against={previous['id']}"
    )
    assert diff.status_code == 200, diff.text
    diff_body = diff.json()
    assert diff_body["changed_fields"] >= 1
    assert any(
        field["path"].startswith("work[")
        for field in diff_body["fields"]
    )

    tex = await client.get(f"/v1/versions/{latest['id']}/export?format=tex")
    assert tex.status_code == 200
    assert "application/x-tex" in tex.headers["content-type"]
    assert "attachment" in tex.headers["content-disposition"]
    assert "\\documentclass" in tex.text
    assert "Jane Doe" in tex.text

    patched = await client.get(
        f"/v1/versions/{latest['id']}/export?format=tex&mode=source"
    )
    assert patched.status_code == 200, patched.text
    assert change["original"] not in patched.text
    assert change["proposed"] in patched.text
    assert int(patched.headers["x-patch-applied"]) >= 1

    change_event = next(
        event for event in latest["change_log"] if event.get("change_id") == change["id"]
    )
    assert change_event["before_text"] == change["original"]
    assert change_event["after_text"] == change["proposed"]

    json_export = await client.get(f"/v1/versions/{latest['id']}/export?format=json")
    assert json_export.status_code == 200
    assert json_export.json()["canonical"]["basics"]["name"] == "Jane Doe"

    docx = await client.get(f"/v1/versions/{latest['id']}/export?format=docx")
    assert docx.status_code == 200
    assert docx.content.startswith(b"PK")
    assert "wordprocessingml" in docx.headers["content-type"]

    pdf = await client.get(f"/v1/versions/{latest['id']}/export?format=pdf")
    assert pdf.status_code == 409
    assert pdf.json()["error"]["code"] == "pdf_export_unavailable"


async def test_version_change_alias_delegates_to_job_decision(client):
    resume, _jd, change, _decision = await _accepted_change(client)
    versions = (await client.get(f"/v1/resumes/{resume['id']}/versions")).json()
    latest = versions[0]

    replay = await client.post(
        f"/v1/versions/{latest['id']}/changes/{change['id']}",
        json={"status": "accepted"},
    )
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["change"]["id"] == change["id"]
    assert body["idempotent_replay"] is True


async def test_source_export_ignores_reverted_change(client):
    resume, _jd, change, decision = await _accepted_change(client)
    rejected = await client.post(
        f"/v1/jobs/{decision['job_id']}/changes/{change['id']}",
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text

    versions = (await client.get(f"/v1/resumes/{resume['id']}/versions")).json()
    patched = await client.get(
        f"/v1/versions/{versions[0]['id']}/export?format=tex&mode=source"
    )
    assert patched.status_code == 200, patched.text
    assert change["original"] in patched.text
    assert change["proposed"] not in patched.text
    assert patched.headers["x-patch-applied"] == "0"


def incoming_original(change: dict) -> str:
    return str(change["original"])


async def test_version_diff_first_version_is_empty(client):
    resume = await upload_sample(client)
    versions = (await client.get(f"/v1/resumes/{resume['id']}/versions")).json()
    first = versions[0]
    diff = await client.get(f"/v1/versions/{first['id']}/diff")
    assert diff.status_code == 200
    assert diff.json()["changed_fields"] == 0
    assert "first version" in diff.json()["note"]

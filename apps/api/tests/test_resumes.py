from __future__ import annotations

import io

import pytest

from tests.conftest import SAMPLE_TEX, upload_sample


async def test_upload_tex_structures_resume(client):
    body = await upload_sample(client)
    document = body["document"]
    assert document["format"] == "tex"
    basics = document["canonical"]["basics"]
    assert basics["name"] == "Jane Doe"
    assert basics["email"] == "jane.doe@example.com"
    assert basics["phone"].endswith("0123")
    assert len(document["canonical"]["work"]) == 2
    assert "Senior Software Engineer" in document["canonical"]["work"][0]["position"]
    assert document["canonical"]["work"][0]["startDate"] == "2021-01"
    assert document["canonical"]["work"][0]["endDate"] == "Present"
    assert len(document["canonical"]["skills"]) == 2
    assert document["structuring"]["method"] == "heuristic"
    assert document["structuring"]["confidence"] >= 0.6
    codes = {issue["code"] for issue in document["issues"]}
    assert "fontawesome" in codes
    assert "missing_name" not in codes


async def test_upload_pdf_without_text_layer_flags_issue(client):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)

    response = await client.post(
        "/v1/resumes", files={"file": ("blank.pdf", buffer.getvalue(), "application/pdf")}
    )
    assert response.status_code == 201, response.text
    issues = {issue["code"] for issue in response.json()["document"]["issues"]}
    assert "pdf_no_text_layer" in issues


async def test_upload_unsupported_format(client):
    response = await client.post(
        "/v1/resumes",
        files={"file": ("notes.xyz", b"just some bytes that are not a resume", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_format"


async def test_upload_too_large(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 8)
    response = await client.post(
        "/v1/resumes", files={"file": ("jane.tex", SAMPLE_TEX.encode(), "application/x-tex")}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"


async def test_hostile_latex_is_rejected(client):
    payload = rb"\documentclass{article}\begin{document}\write18{rm -rf /}\end{document}"
    response = await client.post(
        "/v1/resumes", files={"file": ("evil.tex", payload, "application/x-tex")}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "hostile_latex"
    assert body["error"]["details"]["findings"]


async def test_delete_resume_removes_it(client):
    body = await upload_sample(client)
    resume_id = body["id"]

    deleted = await client.delete(f"/v1/resumes/{resume_id}")
    assert deleted.status_code == 204

    missing = await client.get(f"/v1/resumes/{resume_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "resume_not_found"


async def test_resume_versions_and_list(client):
    body = await upload_sample(client)
    versions = await client.get(f"/v1/resumes/{body['id']}/versions")
    assert versions.status_code == 200
    assert versions.json()[0]["version"] == 1

    listing = await client.get("/v1/resumes")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["name"] == "Jane Doe"


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123"])
async def test_invalid_ids_return_400(client, bad_id):
    response = await client.get(f"/v1/resumes/{bad_id}")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_id"

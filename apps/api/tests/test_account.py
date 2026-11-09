from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.db.models import Resume
from app.db.session import SessionLocal
from tests.conftest import create_sample_jd, upload_sample


async def test_delete_all_removes_rows_and_files(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)
    await client.post("/v1/score", json={"resume_id": resume["id"], "jd_id": jd["id"]})
    await client.post("/v1/facts", json={"fact_text": "Led a team of five engineers."})

    storage_root = Path(settings.storage_dir)
    assert any(path.is_file() for path in storage_root.rglob("*"))

    deleted = await client.delete("/v1/account")
    assert deleted.status_code == 200, deleted.text
    counts = deleted.json()["deleted"]
    assert counts["resumes_deleted"] == 1
    assert counts["scores_deleted"] >= 1
    assert counts["facts_deleted"] == 1
    assert counts["jds_deleted"] == 1
    assert counts["storage_objects_deleted"] >= 1

    assert (await client.get("/v1/resumes")).json()["total"] == 0
    assert (await client.get("/v1/jds")).json()["total"] == 0
    assert (await client.get("/v1/facts")).json()["total"] == 0
    assert (await client.get(f"/v1/resumes/{resume['id']}")).status_code == 404
    assert not any(path.is_file() for path in storage_root.rglob("*"))


async def test_purge_requires_retention_window(client, monkeypatch):
    monkeypatch.setattr(settings, "retention_days", None)
    response = await client.post("/v1/account/purge", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "retention_not_configured"


async def test_purge_deletes_only_expired_resumes(client, monkeypatch):
    old = await upload_sample(client)
    fresh = await upload_sample(client)
    monkeypatch.setattr(settings, "retention_days", 30)

    async with SessionLocal() as session:
        row = await session.get(Resume, UUID(old["id"]))
        assert row is not None
        row.created_at = datetime.now(UTC) - timedelta(days=60)
        await session.commit()

    purged = await client.post("/v1/account/purge", json={})
    assert purged.status_code == 200, purged.text
    assert purged.json()["resumes_deleted"] == 1

    assert (await client.get(f"/v1/resumes/{old['id']}")).status_code == 404
    assert (await client.get(f"/v1/resumes/{fresh['id']}")).status_code == 200

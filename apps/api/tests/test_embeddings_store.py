from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Bullet, JobDescription, ResumeVersion
from app.db.session import SessionLocal
from app.services.scoring.embedding_store import reset_pgvector_state
from tests.conftest import create_sample_jd, upload_sample


async def test_upload_and_jd_persist_embeddings(client):
    resume = await upload_sample(client)
    jd = await create_sample_jd(client)

    async with SessionLocal() as session:
        jd_row = await session.get(JobDescription, UUID(jd["id"]))
        assert jd_row is not None
        assert jd_row.embedding
        assert len(jd_row.embedding) == settings.embedding_dim

        bullets = list(
            (
                await session.execute(
                    select(Bullet)
                    .join(ResumeVersion, ResumeVersion.id == Bullet.resume_version_id)
                    .where(ResumeVersion.resume_id == UUID(resume["id"]))
                )
            ).scalars()
        )
        assert bullets
        assert all(bullet.embedding for bullet in bullets)
        assert any("FastAPI" in bullet.text for bullet in bullets)


async def test_similar_bullets_search_returns_ranked_evidence(client):
    resume = await upload_sample(client)
    reset_pgvector_state()
    response = await client.post(
        "/v1/search/similar-bullets",
        json={"query": "FastAPI production APIs", "resume_id": resume["id"], "limit": 3},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["backend"] == "json"
    assert body["items"]
    assert any("fastapi" in item["text"].lower() for item in body["items"])
    assert body["items"] == sorted(
        body["items"], key=lambda item: item["similarity"], reverse=True
    )


async def test_similar_bullets_falls_back_when_pgvector_unavailable(client, monkeypatch):
    resume = await upload_sample(client)
    monkeypatch.setattr(settings, "embedding_store_backend", "pgvector")
    reset_pgvector_state()
    response = await client.post(
        "/v1/search/similar-bullets",
        json={"query": "PostgreSQL data pipelines", "resume_id": resume["id"]},
    )
    assert response.status_code == 200, response.text
    # SQLite has no pgvector column, so the service must use JSON cosine.
    assert response.json()["backend"] == "json"

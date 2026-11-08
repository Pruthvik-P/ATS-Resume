from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import Fact, Job, JobDescription, Resume
from app.db.session import SessionLocal
from app.schemas.jd import JDAnalysis
from app.schemas.jobs import OptimiseOptions
from app.schemas.resume import ResumeDocument
from app.services.optimiser import run_optimisation
from app.services.scoring.engine import build_score_report

logger = get_logger(__name__)


async def run_optimise_job(job_id: str) -> None:
    job_uuid = UUID(job_id)
    async with SessionLocal() as session:
        job = await session.get(Job, job_uuid)
        if job is None or job.status != "queued":
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.progress = 5
        job.message = "Loading resume and job description"
        await session.commit()

        try:
            payload = job.payload or {}
            resume = await session.get(Resume, UUID(str(payload["resume_id"])))
            jd = await session.get(JobDescription, UUID(str(payload["jd_id"])))
            if resume is None or jd is None:
                raise AppError("job_inputs_missing", "The resume or job description no longer exists.")

            document = ResumeDocument.model_validate(resume.canonical_json)
            analysis = JDAnalysis.model_validate(jd.analysis_json)
            baseline = build_score_report(
                resume_id=str(resume.id), jd_id=str(jd.id), document=document, analysis=analysis
            )

            job.progress = 25
            job.message = "Planning and verifying changes"
            await session.commit()

            facts = (
                await session.execute(select(Fact).where(Fact.user_id == job.user_id))
            ).scalars()
            fact_texts = [fact.fact_text for fact in facts]

            result = await run_optimisation(
                job_id=str(job.id),
                document=document,
                analysis=analysis,
                baseline=baseline,
                facts=fact_texts,
                options=OptimiseOptions.model_validate(payload.get("options") or {}),
                target_score=payload.get("target_score"),
            )

            job.result = result.model_dump(mode="json")
            job.status = "succeeded"
            job.progress = 100
            job.message = "Optimisation proposals ready"
            job.finished_at = datetime.now(UTC)
            await session.commit()
            logger.info(
                "Optimisation finished",
                extra={"job_id": str(job.id), "resume_id": str(resume.id), "jd_id": str(jd.id)},
            )
        except Exception as exc:
            await session.rollback()
            job = await session.get(Job, job_uuid)
            if job is None:
                return
            job.status = "failed"
            job.progress = 100
            job.message = "Optimisation failed"
            job.error = {"code": "optimise_failed", "message": str(exc)}
            job.finished_at = datetime.now(UTC)
            await session.commit()
            logger.exception("Optimisation job failed", extra={"job_id": job_id})

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import facts, jds, jobs, resumes, score

api_router = APIRouter()
api_router.include_router(resumes.router)
api_router.include_router(jds.router)
api_router.include_router(score.router)
api_router.include_router(jobs.router)
api_router.include_router(facts.router)

__all__ = ["api_router"]

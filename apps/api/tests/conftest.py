from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="ats-api-tests-")
os.environ["ATS_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/test.db"
os.environ["ATS_STORAGE_DIR"] = f"{_TMP}/uploads"
os.environ["ATS_ENVIRONMENT"] = "test"
os.environ["ATS_LLM_PROVIDER"] = "stub"
os.environ["ATS_API_KEY"] = ""

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

SAMPLE_TEX = r"""
\documentclass[11pt,letterpaper]{article}
\usepackage[T1]{fontenc}
\usepackage{fontawesome5}
\input{glyphtounicode}
\pdfgentounicode=1
\begin{document}
\begin{center}
{\Huge Jane Doe}\\
jane.doe@example.com | +1 415 555 0123 | linkedin.com/in/janedoe | github.com/janedoe
\end{center}

\section{Summary}
Backend engineer with 6 years of experience building production APIs and data platforms.

\section{Experience}
\resumeSubheading{Senior Software Engineer}{Acme Corp}{Jan 2021}{Present}
\resumeItem{Built FastAPI services handling 2M requests per day.}
\resumeItem{Responsible for leading a team of 5 engineers.}
\resumeSubheading{Software Engineer}{Beta LLC}{Jun 2018}{Dec 2020}
\resumeItem{Developed Python data pipelines with Airflow and PostgreSQL.}
\resumeItem{Reduced batch processing time by 40\% through query tuning.}

\section{Skills}
\resumeItem{Languages: Python, JavaScript, SQL}
\resumeItem{Cloud: AWS, Docker, Kubernetes}

\section{Education}
\resumeItem{Bachelor of Science in Computer Science | State University | 2018}
\end{document}
"""

SAMPLE_JD = """
Senior Backend Engineer at Nimbus

Requirements
- 5+ years of experience building production APIs with Python
- Must have FastAPI and PostgreSQL experience
- Kubernetes and Terraform are required
- Experience with AWS

Nice to have
- Go
- GraphQL

Responsibilities
- Design and maintain CI/CD pipelines
- Build reliable distributed services

Must be authorized to work in the US. No visa sponsorship available.
"""


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def upload_sample(client) -> dict:
    response = await client.post(
        "/v1/resumes",
        files={"file": ("jane.tex", SAMPLE_TEX.encode("utf-8"), "application/x-tex")},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_sample_jd(client) -> dict:
    response = await client.post("/v1/jds", json={"text": SAMPLE_JD, "title": "Senior Backend Engineer"})
    assert response.status_code == 201, response.text
    return response.json()

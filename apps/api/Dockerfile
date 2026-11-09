FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install ".[postgres,pdf]"

COPY alembic.ini ./
COPY alembic ./alembic

# Create the upload path in the image so a named volume mounted here inherits
# the non-root ownership instead of being created root-owned by Docker.
RUN useradd --create-home appuser \
    && mkdir -p /data/uploads \
    && chown -R appuser:appuser /srv/app /data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -fsS http://localhost:8000/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

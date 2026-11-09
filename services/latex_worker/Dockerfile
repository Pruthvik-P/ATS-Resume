# Sandboxed LaTeX compile worker.
#
# Build:
#   docker build -t ats-latex-worker:latest services/latex_worker
#
# Run (Compose does this with the same restrictions):
#   docker run --rm -i --network none --read-only \
#     --tmpfs /tmp:rw,noexec,nosuid,size=256m \
#     --memory 512m --cpus 1 --pids-limit 128 \
#     --cap-drop ALL --security-opt no-new-privileges \
#     ats-latex-worker:latest compile - resume.tex < project.tar.gz > out.tar.gz
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    TEXMFVAR=/tmp/texmf-var \
    TEXMFCONFIG=/tmp/texmf-config \
    TEXMFHOME=/tmp/texmf-home

# TeX Live + latexmk. `texlive-latex-extra` supplies enumitem, geometry, and
# the common resume-template packages; fonts-recommended supplies lmodern.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        latexmk \
        texlive-latex-base \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        lmodern \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 worker \
    && mkdir -p /app \
    && chown worker:worker /app /tmp

COPY --chown=worker:worker worker.py /app/worker.py

USER worker
WORKDIR /app

EXPOSE 8099

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3)" || exit 1

ENTRYPOINT ["python3", "/app/worker.py"]
CMD ["serve"]

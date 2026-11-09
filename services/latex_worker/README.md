# LaTeX worker

Out-of-process, sandboxed LaTeX compiler used by the ingestion and optimiser
pipelines. It has no third-party Python dependencies and exposes:

- `GET /health` → `{"status":"ok","engine":"latexmk", ...}`
- `POST /compile?main=resume.tex` with a `.tar.gz` body → `.tar.gz` response
  containing `main.pdf`, `main.log`, and optional `main.synctex.gz`.

One-shot mode (used by the API's Docker fallback):

```bash
docker run --rm -i --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --memory 512m --cpus 1 --pids-limit 128 \
  --cap-drop ALL --security-opt no-new-privileges \
  ats-latex-worker:latest compile - resume.tex \
  < project.tar.gz > out.tar.gz
```

## Build

```bash
docker build -t ats-latex-worker:latest services/latex_worker
```

## Engine scope

The image targets pdfLaTeX via `latexmk` (Tectonic or `pdflatex` can be used as
alternatives when installed). XeLaTeX/LuaLaTeX-only templates (`fontspec`,
`unicode-math`) are not supported out of the box; adding `texlive-xetex` and an
engine-selection step is the next extension.

## Safety properties

- Non-root `worker` user, read-only root filesystem in Compose.
- Input validation: no absolute paths, `..` traversal, oversized files, or too
  many entries; only common TeX/asset suffixes are extracted.
- Static rejection of `\write18`, `shellesc`, `\openout`, `\immediate\write`,
  `\directlua`, pipe `\input`, and traversal-style includes.
- TeX runs with `shell_escape=f`, `openin_any=p`, `openout_any=p`, and a
  wall-clock timeout (`WORKER_TIMEOUT_SECONDS`, default 45s). `pdflatex` also gets
  `-no-shell-escape`; `latexmk` leaves shell escape off by default.
- Outputs are capped at `WORKER_MAX_OUTPUT_BYTES` (20 MiB).

`COMPILE_TIMEOUT` and output caps are worker-side limits; Compose also applies
container-level CPU, memory, PID, and tmpfs limits.

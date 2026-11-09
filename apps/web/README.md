# ats.resume web

Next.js app for the ATS resume scorer and optimiser. The landing page explains
the method; `/start` is the working intake flow.

## Run it

The FastAPI engine must be running first (see the root README and
`apps/api/README.md`).

```bash
cd apps/web
npm install
cp .env.example .env.local   # Windows: copy .env.example .env.local
npm run dev
```

Open <http://localhost:3000/start>.

## Run it in Docker

The image builds the app with `output: "standalone"`, so the runtime container
carries only the server and its traced dependencies. From the repository root:

```bash
docker compose -f infra/docker-compose.yml up --build
```

Compose starts Postgres, the API, and this app, then serves the UI on
<http://localhost:3000>. Inside the network the app is configured with
`API_BASE_URL=http://api:8000`; nothing needs to run on the host. Set
`ATS_API_KEY` (shell or `infra/.env`) to protect both the API and the proxy with
the same key.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI origin used by the Next server. Prefer `127.0.0.1` over `localhost` to avoid IPv6 resolution surprises. |
| `ATS_API_KEY` | unset | Optional. Sent as `x-api-key` when the engine has a key configured. Must match the API's key. This stays server-side. |

Do not add a `NEXT_PUBLIC_` prefix to either variable: that would expose the key
to the browser.

## How the browser talks to the engine

`src/app/api/backend/[...path]/route.ts` is a small same-origin proxy. The
browser calls `/api/backend/*`, and the Next server forwards only the routes
listed in its allowlist (`health`, `meta`, `resumes`, `jds`, `score`, `scores`,
`optimise`, `jobs`, `facts`). This keeps the API key out of the browser and
avoids CORS. SSE job progress is streamed through the same route; the client
falls back to polling if the stream is unavailable.

## What this build does

- Uploads PDF, DOCX, `.tex` / `.zip`, or `.txt`; extracts text and structures it.
- Analyses a pasted job description into must-have / nice-to-have skills.
- Shows the seven-component score, caps, penalties, parse issues, and
  recommendations from the engine.
- Starts an optimisation job, streams progress, and lets you accept or reject
  each proposal. Accepted proposals trigger a real re-score.
- Keeps `needs_user_input` proposals as questions. They cannot be accepted
  as-is in the UI.

Not implemented here: sandboxed LaTeX compilation, PDF/DOCX export, OCR,
multi-parser ATS comparison, and a trained embedding model. The default LLM is
a deterministic stub. Scores are a calibrated proxy, not ground truth.

## Theming

Light and dark are class-based (`.dark` on `<html>`), not a media-query token
flip. On first visit the app follows the OS preference; the navbar toggle writes
`ats-theme` to `localStorage`, and an inline script in `src/app/layout.tsx`
applies it before the first paint so there is no flash. In dark mode the page,
cards, and controls switch to a deep green-black "darkroom" palette, while the
hero proof sheet, the X-Ray's human panel, and the proposal card stay fixed
paper-white (`sheet` tokens). Terminal-style panels stay dark (`night` tokens).

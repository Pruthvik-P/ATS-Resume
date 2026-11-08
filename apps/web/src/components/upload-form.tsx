"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createJd,
  createOptimise,
  createScore,
  decideChange,
  getJob,
  jobEventsUrl,
  uploadResume,
} from "@/lib/api";
import type {
  JDAnalysisResponse,
  JobEventPayload,
  JobRead,
  OptimiseResult,
  ResumeRead,
  ScoreReport,
} from "@/lib/api-types";
import { ScoreReportPanel } from "@/components/score-report-panel";
import { ParsePanel } from "@/components/parse-panel";
import { JdPanel } from "@/components/jd-panel";
import { OptimiserPanel } from "@/components/optimiser-panel";

type StepKey = "upload" | "jd" | "score" | "optimise";
type Phase =
  | "idle"
  | "uploading"
  | "analysing"
  | "scoring"
  | "optimising"
  | "complete"
  | "error";

type ScanError = {
  step: StepKey;
  code: string;
  message: string;
};

const MAX_MB = 10;
const ACCEPTED_FILE_TYPES = ".pdf,.docx,.tex,.zip,.txt";

const PHASE_INDEX: Record<Phase, number> = {
  idle: -1,
  uploading: 0,
  analysing: 1,
  scoring: 2,
  optimising: 3,
  complete: 4,
  error: -1,
};

const STEP_LABELS: Record<StepKey, string> = {
  upload: "Upload & parse",
  jd: "Analyse the job description",
  score: "Score seven components",
  optimise: "Plan verified edits",
};

const ERROR_HINTS: Record<string, string> = {
  api_unreachable:
    "Start the FastAPI engine on port 8000, then retry. The Next server proxies to API_BASE_URL.",
  network_error:
    "The browser could not reach this Next.js server. Check that the dev server is still running.",
  unsupported_format:
    "Upload a PDF, DOCX, .tex, .zip of LaTeX sources, or a .txt resume.",
  upload_too_large: `The upload limit is ${MAX_MB} MB.`,
  hostile_latex:
    "The LaTeX source contains shell-execution or absolute-path constructs and was rejected. Remove them before uploading.",
  jd_url_blocked:
    "This UI submits pasted text only. URL fetching is blocked by the engine's SSRF guard.",
  unauthorized:
    "The engine has an API key configured. Set ATS_API_KEY on the Next server to the same value.",
  validation_error:
    "The engine rejected the request shape. Check the FastAPI logs for the field that failed.",
};

function normaliseError(error: unknown, step: StepKey): ScanError {
  if (error instanceof ApiError) {
    return { step, code: error.code, message: error.message };
  }
  return {
    step,
    code: "unexpected_error",
    message:
      error instanceof Error
        ? error.message
        : "An unexpected error occurred before the scan could finish.",
  };
}

function SubmitLabel({ phase }: { phase: Phase }) {
  switch (phase) {
    case "uploading":
      return <>Uploading…</>;
    case "analysing":
      return <>Analysing JD…</>;
    case "scoring":
      return <>Scoring…</>;
    case "optimising":
      return <>Optimising…</>;
    default:
      return <>Score &amp; optimise</>;
  }
}

function ScanProgress({
  phase,
  progress,
  resume,
  jd,
  report,
  result,
  job,
  error,
}: {
  phase: Phase;
  progress: number;
  resume: ResumeRead | null;
  jd: JDAnalysisResponse | null;
  report: ScoreReport | null;
  result: OptimiseResult | null;
  job: JobRead | null;
  error: ScanError | null;
}) {
  const steps: Array<{ key: StepKey; detail: string }> = [
    {
      key: "upload",
      detail: resume
        ? `${resume.document.format.toUpperCase()} · ${resume.filename}`
        : "PDF · DOCX · LaTeX · TXT",
    },
    {
      key: "jd",
      detail: jd
        ? `${jd.analysis.must_have.length} must-have · ${jd.analysis.nice_to_have.length} nice-to-have`
        : "paste a description",
    },
    {
      key: "score",
      detail: report
        ? `overall ${report.overall_score.toFixed(1)} · raw ${report.raw_score.toFixed(1)}`
        : "seven weighted components",
    },
    {
      key: "optimise",
      detail: result
        ? `${result.proposals.length} proposals · ${result.iterations} iterations`
        : (job?.message ?? "waiting for the score"),
    },
  ];

  const currentIndex =
    phase === "error"
      ? Math.max(0, steps.findIndex((step) => step.key === error?.step))
      : PHASE_INDEX[phase];

  return (
    <div className="mb-4 border border-line bg-paper">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              phase === "error"
                ? "bg-redline"
                : phase === "complete"
                  ? "bg-ok"
                  : "bg-accent"
            }`}
          />
          <span className="eyebrow text-muted">
            scan / {phase === "error" ? "stopped" : phase === "complete" ? "complete" : "running"}
          </span>
        </div>
        <span className="font-data text-[10px] uppercase tracking-[0.12em] text-muted">
          {Math.round(progress)}%
        </span>
      </div>

      <div className="h-1.5 w-full overflow-hidden bg-line/60">
        <span
          className={`block h-full transition-[width] duration-500 ${
            phase === "error" ? "bg-redline" : phase === "complete" ? "bg-ok" : "bg-accent"
          }`}
          style={{ width: `${Math.max(2, Math.min(100, progress))}%` }}
        />
      </div>

      <ol className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((step, index) => {
          const failed = phase === "error" && error?.step === step.key;
          const done = phase === "complete" || index < currentIndex;
          const active = !failed && index === currentIndex && phase !== "complete";
          return (
            <li key={step.key} className="bg-paper px-4 py-3">
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-4 w-4 items-center justify-center border font-data text-[8px] ${
                    failed
                      ? "border-redline/30 bg-redline-soft text-redline"
                      : done
                        ? "border-ok/30 bg-ok-soft text-ok"
                        : active
                          ? "border-accent/30 bg-accent-soft text-accent"
                          : "border-line bg-bg text-muted"
                  }`}
                >
                  {failed ? "!" : done ? "✓" : index + 1}
                </span>
                <span
                  className={`font-data text-[9px] uppercase tracking-[0.12em] ${
                    active ? "text-ink" : "text-muted"
                  }`}
                >
                  {STEP_LABELS[step.key]}
                </span>
              </div>
              <p className="mt-1.5 truncate text-[10px] text-muted" title={step.detail}>
                {step.detail}
              </p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function ErrorPanel({
  error,
  onRetry,
}: {
  error: ScanError;
  onRetry: () => void;
}) {
  const hint = ERROR_HINTS[error.code];
  return (
    <div className="border border-redline/25 bg-redline-soft p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-redline" />
          <span className="eyebrow text-redline">
            stopped at {STEP_LABELS[error.step]}
          </span>
        </div>
        <span className="font-data text-[9px] uppercase tracking-[0.12em] text-redline/80">
          {error.code}
        </span>
      </div>
      <p className="mt-2 text-small leading-relaxed text-ink">{error.message}</p>
      {hint && (
        <p className="mt-2 border-l-2 border-redline/40 pl-3 text-caption leading-relaxed text-ink/70">
          {hint}
        </p>
      )}
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 inline-flex h-8 items-center border border-redline/30 bg-paper px-3 font-data text-[10px] font-medium uppercase tracking-[0.1em] text-redline transition-colors hover:bg-redline-soft"
      >
        Retry this scan ↻
      </button>
    </div>
  );
}

export function UploadForm() {
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");
  const [dragging, setDragging] = useState(false);

  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<ScanError | null>(null);

  const [resume, setResume] = useState<ResumeRead | null>(null);
  const [jd, setJd] = useState<JDAnalysisResponse | null>(null);
  const [report, setReport] = useState<ScoreReport | null>(null);
  const [job, setJob] = useState<JobRead | null>(null);
  const [result, setResult] = useState<OptimiseResult | null>(null);

  const [pendingChangeId, setPendingChangeId] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const busy =
    phase === "uploading" ||
    phase === "analysing" ||
    phase === "scoring" ||
    phase === "optimising";
  const jobId = job?.id ?? null;

  useEffect(() => {
    if (phase !== "optimising" || !jobId) return;

    let cancelled = false;
    let finished = false;
    let gotEvent = false;
    let pollBusy = false;
    let pollFailures = 0;
    let source: EventSource | null = null;
    let poll: number | null = null;
    let watchdog: number | null = null;

    const stop = () => {
      if (watchdog !== null) {
        window.clearTimeout(watchdog);
        watchdog = null;
      }
      if (poll !== null) {
        window.clearInterval(poll);
        poll = null;
      }
      source?.close();
      source = null;
    };

    const fail = (message: string, code = "optimise_failed") => {
      if (cancelled || finished) return;
      finished = true;
      setError({ step: "optimise", code, message });
      setPhase("error");
      stop();
    };

    const finish = (next: OptimiseResult) => {
      if (cancelled || finished) return;
      finished = true;
      setResult(next);
      setProgress(100);
      setJob((current) =>
        current
          ? {
              ...current,
              status: "succeeded",
              progress: 100,
              message: "Optimisation proposals ready",
              result: next,
            }
          : current,
      );
      setPhase("complete");
      stop();
    };

    const applyPatch = (patch: Partial<JobRead>) => {
      if (cancelled || finished) return;
      setJob((current) => (current ? { ...current, ...patch } : current));
      if (typeof patch.progress === "number") {
        setProgress((current) =>
          Math.max(current, 72 + Math.min(100, patch.progress ?? 0) * 0.28),
        );
      }
      if (patch.status === "succeeded" && patch.result) {
        finish(patch.result);
      } else if (patch.status === "failed" || patch.status === "cancelled") {
        fail(
          patch.error?.message ??
            "The optimisation job stopped before it produced proposals.",
          patch.error?.code ?? "optimise_failed",
        );
      }
    };

    const pollNow = async () => {
      if (cancelled || finished || pollBusy) return;
      pollBusy = true;
      try {
        const current = await getJob(jobId);
        if (cancelled) return;
        pollFailures = 0;
        applyPatch(current);
      } catch (pollError) {
        pollFailures += 1;
        if (pollFailures >= 4 && !cancelled && !finished) {
          const scanError = normaliseError(pollError, "optimise");
          fail(scanError.message, scanError.code);
        }
      } finally {
        pollBusy = false;
      }
    };

    const startPolling = () => {
      if (poll !== null || cancelled || finished) return;
      poll = window.setInterval(() => {
        void pollNow();
      }, 900);
    };

    const onEvent = (event: Event) => {
      gotEvent = true;
      const message = event as MessageEvent<string>;
      if (typeof message.data !== "string") return;
      try {
        const payload = JSON.parse(message.data) as JobEventPayload;
        applyPatch({
          status: payload.status,
          progress: payload.progress,
          message: payload.message,
          error: payload.error,
          result: payload.result,
        });
      } catch {
        // A malformed stream frame is not fatal; polling still runs.
      }
    };

    source = new EventSource(jobEventsUrl(jobId));
    ["status", "progress", "done"].forEach((eventName) => {
      source?.addEventListener(eventName, onEvent);
    });

    source.addEventListener("error", (event) => {
      const message = event as MessageEvent<string>;
      if (typeof message.data === "string" && message.data) {
        onEvent(event);
        return;
      }
      // A real connection failure: keep the job alive and poll it.
      startPolling();
    });

    // If the stream is buffered or blocked, start polling shortly after.
    watchdog = window.setTimeout(() => {
      if (!gotEvent && !cancelled && !finished) startPolling();
    }, 2500);

    return () => {
      cancelled = true;
      stop();
    };
  }, [phase, jobId]);

  const runScan = async () => {
    if (!resumeFile || !jdText.trim() || busy) return;

    setError(null);
    setResume(null);
    setJd(null);
    setReport(null);
    setJob(null);
    setResult(null);
    setDecisionError(null);
    setPendingChangeId(null);
    setProgress(8);
    setPhase("uploading");

    let step: StepKey = "upload";
    try {
      const uploaded = await uploadResume(resumeFile);
      setResume(uploaded);
      setProgress(28);

      step = "jd";
      setPhase("analysing");
      const analysed = await createJd(jdText.trim());
      setJd(analysed);
      setProgress(52);

      step = "score";
      setPhase("scoring");
      const scored = await createScore(uploaded.id, analysed.id);
      setReport(scored);
      setProgress(72);

      step = "optimise";
      setPhase("optimising");
      const queued = await createOptimise(uploaded.id, analysed.id);
      setJob(queued);
      setProgress(74);

      window.requestAnimationFrame(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } catch (scanError) {
      setError(normaliseError(scanError, step));
      setPhase("error");
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void runScan();
  };

  const handleResumeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setResumeFile(file);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) setResumeFile(file);
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(true);
  };

  const handleDecision = async (
    changeId: string,
    status: "accepted" | "rejected",
  ) => {
    if (!job || !result) return;
    setPendingChangeId(changeId);
    setDecisionError(null);
    try {
      const decision = await decideChange(job.id, changeId, status);
      setResult((current) =>
        current
          ? {
              ...current,
              score_after_accepted: decision.score_after_accepted,
              proposals: current.proposals.map((proposal) =>
                proposal.id === decision.change.id ? decision.change : proposal,
              ),
            }
          : current,
      );
    } catch (decisionFailure) {
      const scanError = normaliseError(decisionFailure, "optimise");
      setDecisionError(scanError.message);
    } finally {
      setPendingChangeId(null);
    }
  };

  const resetScan = () => {
    setPhase("idle");
    setProgress(0);
    setError(null);
    setResume(null);
    setJd(null);
    setReport(null);
    setJob(null);
    setResult(null);
    setDecisionError(null);
    setPendingChangeId(null);
    setResumeFile(null);
    setJdText("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const wordCount = jdText.trim()
    ? jdText.trim().split(/\s+/).filter(Boolean).length
    : 0;
  const showResults = phase !== "idle";

  return (
    <>
      <section className="mx-auto max-w-[1240px] px-5 py-12 sm:px-8 sm:py-16">
        <form onSubmit={handleSubmit}>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[0.85fr_1.15fr]">
            <div className="border border-line bg-paper">
              <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
                <span className="eyebrow text-muted">01 / resume</span>
                <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                  PDF · DOCX · TEX · TXT
                </span>
              </div>
              <div className="p-4">
                <div className="mb-4">
                  <h2 className="text-h3 text-ink">Your source document</h2>
                  <p className="mt-1 text-caption text-muted">
                    Up to {MAX_MB} MB. LaTeX is read as source text, not compiled.
                  </p>
                </div>

                <div
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  onDragLeave={() => setDragging(false)}
                  className={`border border-dashed p-6 text-center transition-colors ${
                    dragging
                      ? "border-accent bg-accent-soft"
                      : resumeFile
                        ? "border-ok/50 bg-ok-soft/50"
                        : "border-line bg-bg/40 hover:border-accent/50 hover:bg-accent-soft/40"
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    id="resume-upload"
                    type="file"
                    accept={ACCEPTED_FILE_TYPES}
                    className="sr-only"
                    onChange={handleResumeChange}
                  />
                  <label
                    htmlFor="resume-upload"
                    className="flex min-h-[210px] cursor-pointer flex-col items-center justify-center"
                  >
                    <span className="mx-auto flex h-10 w-10 items-center justify-center border border-line bg-paper font-data text-sm text-accent">
                      ↑
                    </span>
                    {resumeFile ? (
                      <>
                        <p className="mt-3 break-all text-small font-semibold text-ink">
                          {resumeFile.name}
                        </p>
                        <p className="mt-1 font-data text-[9px] uppercase tracking-[0.12em] text-ok">
                          ready · {Math.round(resumeFile.size / 1024)} KB
                        </p>
                        <p className="mt-3 font-data text-[9px] text-muted underline underline-offset-4">
                          choose a different file
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="mt-3 text-small font-semibold text-ink">
                          Choose a resume file
                        </p>
                        <p className="mt-1 text-caption text-muted">
                          or drag it into this box
                        </p>
                      </>
                    )}
                  </label>
                </div>

                <ul className="mt-4 space-y-1.5 font-data text-[9px] leading-relaxed text-muted">
                  <li className="flex gap-2">
                    <span className="text-ok">✓</span> source map kept for parsed
                    fields
                  </li>
                  <li className="flex gap-2">
                    <span className="text-ok">✓</span> PDF text extraction;
                    scanned-image OCR is not enabled
                  </li>
                  <li className="flex gap-2">
                    <span className="text-ok">✓</span> never used to invent
                    experience
                  </li>
                </ul>
              </div>
            </div>

            <div className="border border-line bg-paper">
              <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
                <span className="eyebrow text-muted">02 / job description</span>
                <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                  paste text
                </span>
              </div>
              <div className="p-4">
                <div className="mb-4">
                  <h2 className="text-h3 text-ink">The role you want</h2>
                  <p className="mt-1 text-caption text-muted">
                    Paste the full posting, including requirements and
                    nice-to-haves.
                  </p>
                </div>
                <textarea
                  value={jdText}
                  onChange={(event) => setJdText(event.target.value)}
                  placeholder="Paste the job description here…"
                  className="min-h-[300px] w-full resize-y border border-line bg-bg/40 p-4 text-small leading-relaxed text-ink outline-none transition-colors placeholder:text-muted/70 focus:border-accent focus:bg-paper"
                  rows={12}
                />
                <div className="mt-3 flex items-center justify-between gap-4">
                  <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                    {wordCount > 0
                      ? `${wordCount.toLocaleString()} words`
                      : "waiting for a description"}
                  </span>
                  {jdText.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setJdText("")}
                      className="font-data text-[9px] uppercase tracking-[0.12em] text-muted underline underline-offset-4 transition-colors hover:text-ink"
                    >
                      clear
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-5 border border-line bg-paper p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
            <div>
              <p className="max-w-xl text-caption leading-relaxed text-muted">
                Your resume is uploaded to the engine and stored on the scan host
                (SQLite or Postgres, plus local file storage). Nothing is sent to
                an employer. No claim is added unless it traces back to your
                source.
              </p>
              <p className="mt-2 max-w-xl font-data text-[9px] leading-relaxed text-muted">
                Scores are a calibrated proxy, not ground truth. PDF extraction
                uses pypdf/PyMuPDF; the optimiser runs a deterministic stub unless
                an LLM provider is configured.
              </p>
            </div>
            <button
              type="submit"
              disabled={!resumeFile || !jdText.trim() || busy}
              className="inline-flex h-12 shrink-0 items-center justify-center gap-3 bg-ink px-6 text-small font-semibold text-paper transition-colors hover:bg-ink-2 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <SubmitLabel phase={phase} />
              <span aria-hidden="true" className="font-data text-[12px]">
                →
              </span>
            </button>
          </div>
        </form>
      </section>

      {showResults && (
        <section
          ref={resultsRef}
          id="scan-results"
          className="mx-auto max-w-[1240px] scroll-mt-20 px-5 pb-16 sm:px-8 sm:pb-24"
        >
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="eyebrow text-muted">scan / result</span>
            </div>
            <button
              type="button"
              onClick={resetScan}
              className="font-data text-[9px] uppercase tracking-[0.12em] text-muted underline underline-offset-4 transition-colors hover:text-ink"
            >
              new scan ↻
            </button>
          </div>

          <ScanProgress
            phase={phase}
            progress={progress}
            resume={resume}
            jd={jd}
            report={report}
            result={result}
            job={job}
            error={error}
          />

          {error && <ErrorPanel error={error} onRetry={() => void runScan()} />}

          <div className="mt-4 space-y-5">
            {report && <ScoreReportPanel report={report} />}

            {(phase === "optimising" || job || result) && (
              <OptimiserPanel
                job={job}
                result={result}
                progress={progress}
                onDecide={(changeId, status) =>
                  void handleDecision(changeId, status)
                }
                pendingChangeId={pendingChangeId}
                decisionError={decisionError}
              />
            )}

            {jd && <JdPanel jd={jd} />}
            {resume && report && <ParsePanel resume={resume} report={report} />}
          </div>
        </section>
      )}
    </>
  );
}

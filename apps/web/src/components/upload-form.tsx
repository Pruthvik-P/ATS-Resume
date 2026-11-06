"use client";

import { useState } from "react";

type FileKind = "resume" | "jd";

export function UploadForm() {
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState(false);
  const [dragging, setDragging] = useState(false);

  const handleResumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setResumeFile(file);
    setNotice(false);
  };

  const handleDrop = (kind: FileKind) => (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (kind === "resume") setResumeFile(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!resumeFile || !jdText.trim()) return;
    setSubmitting(true);
    setNotice(false);
    window.setTimeout(() => {
      setSubmitting(false);
      setNotice(true);
    }, 700);
  };

  const acceptResume = ".pdf,.docx,.tex,.zip";
  const maxMB = 10;
  const wordCount = jdText.trim()
    ? jdText.trim().split(/\s+/).filter(Boolean).length
    : 0;

  return (
    <section className="mx-auto max-w-[1240px] px-5 py-12 sm:px-8 sm:py-16">
      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[0.85fr_1.15fr]">
          {/* Resume upload */}
          <div className="border border-line bg-paper">
            <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
              <span className="eyebrow text-muted">01 / resume</span>
              <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                PDF · DOCX · TEX
              </span>
            </div>
            <div className="p-4">
              <div className="mb-4">
                <h2 className="text-h3 text-ink">Your source document</h2>
                <p className="mt-1 text-caption text-muted">
                  Up to {maxMB} MB. LaTeX is parsed as source, not flattened.
                </p>
              </div>

              <div
                onDrop={handleDrop("resume")}
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
                  id="resume-upload"
                  type="file"
                  accept={acceptResume}
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
                  <span className="text-ok">✓</span> source map kept for every
                  field
                </li>
                <li className="flex gap-2">
                  <span className="text-ok">✓</span> sandboxed LaTeX compile, no
                  network
                </li>
                <li className="flex gap-2">
                  <span className="text-ok">✓</span> never used to invent
                  experience
                </li>
              </ul>
            </div>
          </div>

          {/* Job description */}
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
                onChange={(e) => {
                  setJdText(e.target.value);
                  setNotice(false);
                }}
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
                    onClick={() => {
                      setJdText("");
                      setNotice(false);
                    }}
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
              Your resume and job description stay attached to this scan. No
              change is submitted anywhere, and no claim is added unless it
              traces back to your source.
            </p>
            {notice && (
              <p
                aria-live="polite"
                className="mt-3 border-l-2 border-signal pl-3 font-data text-[10px] leading-relaxed text-signal"
              >
                This is a frontend preview. The score engine and LaTeX worker
                are wired next — your files were not uploaded.
              </p>
            )}
          </div>
          <button
            type="submit"
            disabled={!resumeFile || !jdText.trim() || submitting}
            className="inline-flex h-12 shrink-0 items-center justify-center gap-3 bg-ink px-6 text-small font-semibold text-paper transition-colors hover:bg-ink-2 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? "Scoring…" : "Score & optimise"}
            <span aria-hidden="true" className="font-data text-[12px]">
              →
            </span>
          </button>
        </div>
      </form>
    </section>
  );
}

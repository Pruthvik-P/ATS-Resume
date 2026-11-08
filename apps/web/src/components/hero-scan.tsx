"use client";

import { useState } from "react";

export function HeroScan() {
  const [run, setRun] = useState(0);

  return (
    <div className="relative mx-auto w-full max-w-[520px] lg:mx-0">
      {/* Ghost sheet behind the proof */}
      <div
        aria-hidden="true"
        className="absolute -right-2.5 top-4 h-full w-full border border-sheet-line/70 bg-sheet/40"
      />

      <div className="relative border border-white/10 bg-night shadow-[0_30px_80px_-30px_rgba(0,0,0,0.65)]">
        {/* Toolbar */}
        <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2 font-data text-[10px] uppercase tracking-[0.16em] text-slate-400">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
            <span className="truncate">parsed</span>
            <span className="text-slate-600">/</span>
            <span className="truncate text-slate-300">jane_doe.tex</span>
          </div>
          <span className="shrink-0 border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 font-data text-[9px] font-medium text-amber-300">
            sample issues
          </span>
        </div>

        {/* The sheet */}
        <div className="relative overflow-hidden bg-[#0C120D] p-2.5 sm:p-3.5">
          <div className="relative overflow-hidden bg-sheet px-4 py-5 text-sheet-ink sm:px-6 sm:py-6">
            <div
              aria-hidden="true"
              className="dot-grid pointer-events-none absolute inset-0 opacity-30"
            />

            <div key={run} className="scan-beam" aria-hidden="true" />

            <div className="relative">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-display text-[1.05rem] font-bold leading-tight tracking-[-0.02em]">
                    Jane A. Developer
                  </p>
                  <p className="mt-1 font-data text-[8px] leading-relaxed text-sheet-muted">
                    Senior Software Engineer · jane@example.com · (555) 123-4567
                  </p>
                </div>
                <div className="shrink-0 border border-sheet-ink/15 px-2 py-1 text-right">
                  <p className="font-data text-[7px] uppercase tracking-[0.18em] text-sheet-muted">
                    match
                  </p>
                  <p className="font-display text-[1.55rem] font-bold leading-none">
                    78
                    <span className="font-data text-[8px] font-normal text-sheet-muted">
                      /100
                    </span>
                  </p>
                </div>
              </div>

              <div className="mt-4 border-t border-sheet-ink/15 pt-3">
                <p className="font-data text-[8px] uppercase tracking-[0.2em] text-sheet-muted">
                  Experience
                </p>
                <div className="mt-2">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-[10px] font-semibold">
                      Staff Engineer — Acme Corp
                    </p>
                    <p className="font-data text-[8px] text-sheet-muted">2020—now</p>
                  </div>
                  <p className="mt-1.5 text-[9px] leading-relaxed text-sheet-ink/80">
                    • Led a team of 6 to migrate the monolith to AWS, cutting
                    deploy time 40%.
                  </p>
                  <p className="mt-1 text-[9px] leading-relaxed text-sheet-ink/80">
                    • Designed CI/CD pipelines with GitHub Actions and
                    Terraform.
                  </p>
                </div>
              </div>

              <div className="mt-3 border-t border-sheet-ink/15 pt-3">
                <div className="flex items-center justify-between">
                  <p className="font-data text-[8px] uppercase tracking-[0.2em] text-sheet-muted">
                    Skills
                  </p>
                  <span className="font-data text-[7px] text-sheet-redline">
                    ↓ extraction fails here
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {["Python", "AWS", "Docker", "Go"].map((skill) => (
                    <span
                      key={skill}
                      className="border border-sheet-ink/15 px-1.5 py-0.5 font-data text-[8px] text-sheet-ink/80"
                    >
                      {skill}
                    </span>
                  ))}
                  <span className="border border-sheet-redline/40 bg-sheet-redline/5 px-1.5 py-0.5 font-data text-[8px] text-sheet-redline">
                    [image — 0 chars]
                  </span>
                </div>
                <div className="mt-2 border-l-2 border-sheet-redline bg-sheet-redline/5 px-2 py-1.5">
                  <p className="font-data text-[8px]">P y t h o n · A W S</p>
                  <p className="mt-0.5 font-data text-[7px] text-sheet-redline">
                    spaced-out letters — icon font not extractable
                  </p>
                </div>
                <div className="mt-1.5 border-l-2 border-sheet-redline bg-sheet-redline/5 px-2 py-1.5">
                  <p className="font-data text-[8px]">ﬁnance ﬂow ﬃ</p>
                  <p className="mt-0.5 font-data text-[7px] text-sheet-redline">
                    ligature glyphs returned instead of &quot;fi&quot; / &quot;fl&quot;
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Readout */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-white/10 px-4 py-3">
          <span className="font-data text-[9px] uppercase tracking-[0.16em] text-slate-500">
            extracted
          </span>
          <span className="font-data text-[10px] text-slate-300">1,284 chars</span>
          <span className="font-data text-[10px] text-rose-300">3 issues</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="font-data text-[9px] uppercase tracking-[0.16em] text-slate-500">
              parse fidelity
            </span>
            <span className="font-data text-sm font-semibold text-on-night">82</span>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-white/10 px-4 py-2.5">
          <span className="font-data text-[9px] text-slate-500">
            pypdf · heuristic structurer
          </span>
          <button
            type="button"
            onClick={() => setRun((value) => value + 1)}
            className="font-data text-[9px] uppercase tracking-[0.14em] text-slate-300 underline decoration-slate-600 underline-offset-4 transition-colors hover:text-on-night"
          >
            replay scan ↻
          </button>
        </div>
      </div>
    </div>
  );
}

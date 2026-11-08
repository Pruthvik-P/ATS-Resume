"use client";

import { useState } from "react";

type Decision = "idle" | "accepted" | "rejected";

export function ChangeCard() {
  const [decision, setDecision] = useState<Decision>("idle");

  const original =
    "Worked on building backend services and helped improve performance.";
  const optimised =
    "Built backend services and helped improve performance.";

  return (
    <div className="border border-sheet-ink/15 bg-sheet shadow-[0_24px_60px_-36px_rgba(0,0,0,0.55)]">
      <div className="flex items-center justify-between gap-3 border-b border-sheet-line px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2 font-data text-[10px] uppercase tracking-[0.14em] text-sheet-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-sheet-ok" />
          optimiser
          <span className="text-sheet-line">/</span>
          sample proposal
        </div>
        <span className="border border-sheet-ok/25 bg-sheet-ok/10 px-2 py-0.5 font-data text-[9px] font-medium uppercase tracking-[0.1em] text-sheet-ok">
          verified
        </span>
      </div>

      <div className="flex items-center gap-3 border-b border-sheet-line px-4 py-4 sm:px-5">
        <span className="font-data text-[9px] uppercase tracking-[0.16em] text-sheet-muted">
          change
        </span>
        <span className="font-data text-sm text-sheet-ink">rewrite bullet</span>
        <span className="ml-auto font-data text-[9px] uppercase tracking-[0.1em] text-sheet-muted">
          weak phrase → past tense
        </span>
      </div>

      <div className="space-y-3 px-4 py-4 sm:px-5">
        <div className="border border-sheet-redline/25 bg-sheet-redline-soft/60 p-3">
          <div className="mb-1.5 flex items-center gap-2 font-data text-[9px] uppercase tracking-[0.16em] text-sheet-redline">
            <span aria-hidden="true">−</span> original
          </div>
          <p className="text-small leading-relaxed text-sheet-ink/70">{original}</p>
        </div>

        <div className="border border-sheet-ok/25 bg-sheet-ok-soft/70 p-3">
          <div className="mb-1.5 flex items-center gap-2 font-data text-[9px] uppercase tracking-[0.16em] text-sheet-ok">
            <span aria-hidden="true">+</span> optimised
          </div>
          <p className="text-small leading-relaxed text-sheet-ink">{optimised}</p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {["source: work[0].highlights[2]", "no new facts", "no new numbers"].map(
              (tag) => (
                <span
                  key={tag}
                  className="border border-sheet-line bg-sheet px-1.5 py-0.5 font-data text-[9px] text-sheet-muted"
                >
                  {tag}
                </span>
              ),
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-sheet-line px-4 py-3 sm:px-5">
        {decision === "idle" ? (
          <>
            <button
              type="button"
              onClick={() => setDecision("accepted")}
              className="inline-flex h-8 items-center bg-sheet-ok px-3 font-data text-[10px] font-semibold uppercase tracking-[0.1em] text-sheet transition-colors hover:bg-sheet-ok/90"
            >
              Accept
            </button>
            <button
              type="button"
              onClick={() => setDecision("rejected")}
              className="inline-flex h-8 items-center border border-sheet-line px-3 font-data text-[10px] font-medium uppercase tracking-[0.1em] text-sheet-ink transition-colors hover:bg-sheet-bg"
            >
              Reject
            </button>
            <span className="ml-auto font-data text-[9px] text-sheet-muted">
              you approve every edit
            </span>
          </>
        ) : (
          <>
            <span
              aria-live="polite"
              className={`font-data text-[10px] ${
                decision === "accepted" ? "text-sheet-ok" : "text-sheet-redline"
              }`}
            >
              {decision === "accepted"
                ? "✓ accepted — included in the re-score"
                : "✕ rejected — original kept"}
            </span>
            <button
              type="button"
              onClick={() => setDecision("idle")}
              className="ml-auto font-data text-[9px] uppercase tracking-[0.1em] text-sheet-muted underline underline-offset-4 transition-colors hover:text-sheet-ink"
            >
              try again
            </button>
          </>
        )}
      </div>

      <div className="border-t border-sheet-line bg-sheet-bg/60 px-4 py-2.5 sm:px-5">
        <p className="font-data text-[9px] leading-relaxed text-sheet-muted">
          no metric in your source? the engine inserts{" "}
          <span className="text-sheet-signal">[ADD METRIC: …]</span> and asks you for
          the real number. This build has no PDF or DOCX export.
        </p>
      </div>
    </div>
  );
}

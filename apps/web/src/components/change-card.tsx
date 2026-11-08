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
    <div className="border border-ink/15 bg-paper shadow-[0_24px_60px_-36px_rgba(15,20,15,0.5)]">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2 font-data text-[10px] uppercase tracking-[0.14em] text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-ok" />
          optimiser
          <span className="text-line">/</span>
          sample proposal
        </div>
        <span className="border border-ok/25 bg-ok/10 px-2 py-0.5 font-data text-[9px] font-medium uppercase tracking-[0.1em] text-ok">
          verified
        </span>
      </div>

      <div className="flex items-center gap-3 border-b border-line px-4 py-4 sm:px-5">
        <span className="font-data text-[9px] uppercase tracking-[0.16em] text-muted">
          change
        </span>
        <span className="font-data text-sm text-ink">rewrite bullet</span>
        <span className="ml-auto font-data text-[9px] uppercase tracking-[0.1em] text-muted">
          weak phrase → past tense
        </span>
      </div>

      <div className="space-y-3 px-4 py-4 sm:px-5">
        <div className="border border-redline/25 bg-redline-soft/60 p-3">
          <div className="mb-1.5 flex items-center gap-2 font-data text-[9px] uppercase tracking-[0.16em] text-redline">
            <span aria-hidden="true">−</span> original
          </div>
          <p className="text-small leading-relaxed text-ink/70">{original}</p>
        </div>

        <div className="border border-ok/25 bg-ok-soft/70 p-3">
          <div className="mb-1.5 flex items-center gap-2 font-data text-[9px] uppercase tracking-[0.16em] text-ok">
            <span aria-hidden="true">+</span> optimised
          </div>
          <p className="text-small leading-relaxed text-ink">{optimised}</p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {["source: work[0].highlights[2]", "no new facts", "no new numbers"].map(
              (tag) => (
                <span
                  key={tag}
                  className="border border-line bg-paper px-1.5 py-0.5 font-data text-[9px] text-muted"
                >
                  {tag}
                </span>
              ),
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3 sm:px-5">
        {decision === "idle" ? (
          <>
            <button
              type="button"
              onClick={() => setDecision("accepted")}
              className="inline-flex h-8 items-center bg-ok px-3 font-data text-[10px] font-semibold uppercase tracking-[0.1em] text-paper transition-colors hover:bg-[#175B3C]"
            >
              Accept
            </button>
            <button
              type="button"
              onClick={() => setDecision("rejected")}
              className="inline-flex h-8 items-center border border-line px-3 font-data text-[10px] font-medium uppercase tracking-[0.1em] text-ink transition-colors hover:bg-bg"
            >
              Reject
            </button>
            <span className="ml-auto font-data text-[9px] text-muted">
              you approve every edit
            </span>
          </>
        ) : (
          <>
            <span
              aria-live="polite"
              className={`font-data text-[10px] ${
                decision === "accepted" ? "text-ok" : "text-redline"
              }`}
            >
              {decision === "accepted"
                ? "✓ accepted — included in the re-score"
                : "✕ rejected — original kept"}
            </span>
            <button
              type="button"
              onClick={() => setDecision("idle")}
              className="ml-auto font-data text-[9px] uppercase tracking-[0.1em] text-muted underline underline-offset-4 transition-colors hover:text-ink"
            >
              try again
            </button>
          </>
        )}
      </div>

      <div className="border-t border-line bg-bg/50 px-4 py-2.5 sm:px-5">
        <p className="font-data text-[9px] leading-relaxed text-muted">
          no metric in your source? the engine inserts{" "}
          <span className="text-signal">[ADD METRIC: …]</span> and asks you for
          the real number. This build has no PDF or DOCX export.
        </p>
      </div>
    </div>
  );
}

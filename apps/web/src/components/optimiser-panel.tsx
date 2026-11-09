import type { JobRead, OptimiseResult } from "@/lib/api-types";
import { formatNumber, percent, plural } from "@/lib/format";
import { ProposalCard } from "@/components/proposal-card";

const STOPPED_REASON: Record<OptimiseResult["stopped_reason"], string> = {
  target_reached: "Target score reached",
  no_further_gains: "No further verified gains",
  max_iterations: "Iteration limit reached",
  failed: "Stopped on an error",
};

function SummaryMetric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="bg-paper px-4 py-3">
      <p className="font-data text-[9px] uppercase tracking-[0.14em] text-muted">
        {label}
      </p>
      <p className="mt-1 font-display text-lg font-semibold leading-none text-ink">
        {value}
      </p>
      <p className="mt-1 font-data text-[9px] leading-relaxed text-muted">
        {hint}
      </p>
    </div>
  );
}

function ProgressBody({
  job,
  progress,
}: {
  job: JobRead | null;
  progress: number;
}) {
  const message = job?.message ?? "Queued";
  const status = job?.status ?? "queued";

  return (
    <div className="border border-line bg-paper p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
          </span>
          <span className="eyebrow text-muted">optimiser / running</span>
        </div>
        <span className="font-data text-[10px] uppercase tracking-[0.12em] text-muted">
          {status} · {Math.round(progress)}%
        </span>
      </div>
      <p aria-live="polite" className="mt-3 text-small font-medium text-ink">
        {message}
      </p>
      <div className="mt-3 h-1.5 w-full overflow-hidden bg-line/70">
        <span
          className="block h-full bg-accent transition-[width] duration-500"
          style={{ width: `${Math.max(2, Math.min(100, progress))}%` }}
        />
      </div>
      <div className="mt-4 grid gap-2 font-data text-[9px] uppercase tracking-[0.1em] text-muted sm:grid-cols-3">
        <span>01 · load inputs</span>
        <span>02 · plan + verify edits</span>
        <span>03 · re-score proposals</span>
      </div>
      <p className="mt-4 border-t border-line pt-3 text-caption leading-relaxed text-muted">
        The optimiser can take a few seconds. It only proposes edits; nothing is
        applied until you accept it. Progress streams from the engine, with
        polling as a fallback.
      </p>
    </div>
  );
}

export function OptimiserPanel({
  job,
  result,
  progress,
  onDecide,
  onEdit,
  pendingChangeId,
  decisionError,
}: {
  job: JobRead | null;
  result: OptimiseResult | null;
  progress: number;
  onDecide: (
    changeId: string,
    status: "accepted" | "rejected",
    proposed?: string,
  ) => void;
  onEdit: (changeId: string, proposed: string) => Promise<void>;
  pendingChangeId: string | null;
  decisionError: string | null;
}) {
  if (!result) {
    return <ProgressBody job={job} progress={progress} />;
  }

  const verified = result.proposals.filter(
    (proposal) => proposal.truthfulness === "verified",
  );
  const questions = result.proposals.filter(
    (proposal) => proposal.truthfulness === "needs_user_input",
  );
  const rejectedByVerifier = result.proposals.filter(
    (proposal) => proposal.truthfulness === "rejected",
  );
  const accepted = result.proposals.filter(
    (proposal) => proposal.status === "accepted",
  );
  const rejected = result.proposals.filter(
    (proposal) => proposal.status === "rejected",
  );
  const hasDecided = accepted.length + rejected.length > 0;
  const projectedLabel = hasDecided
    ? "score with accepted edits"
    : "projected after verified edits";
  const scoreDelta = result.score_after_accepted - result.baseline_score;

  return (
    <section className="space-y-4">
      <div className="border border-line bg-paper">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" />
            <span className="eyebrow text-muted">optimiser / proposals</span>
          </div>
          <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
            {result.iterations} iteration{result.iterations === 1 ? "" : "s"} ·{" "}
            {STOPPED_REASON[result.stopped_reason]}
          </span>
        </div>

        <div className="grid gap-px border-b border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          <SummaryMetric
            label="baseline"
            value={formatNumber(result.baseline_score)}
            hint="before any edits"
          />
          <SummaryMetric
            label={projectedLabel}
            value={formatNumber(result.score_after_accepted)}
            hint={
              scoreDelta === 0
                ? "no verified gain so far"
                : `${scoreDelta > 0 ? "+" : ""}${formatNumber(scoreDelta)} points`
            }
          />
          <SummaryMetric
            label="target"
            value={formatNumber(result.target_score)}
            hint="optimiser stopping target"
          />
          <SummaryMetric
            label="decisions"
            value={`${accepted.length} / ${result.proposals.length}`}
            hint={`${plural(rejected.length, "rejected")} · ${plural(questions.filter((item) => item.status === "pending").length, "open question")}`}
          />
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3 font-data text-[9px] uppercase tracking-[0.1em] text-muted">
          <span>
            verifier checked{" "}
            <span className="text-ink">{result.verifier.checked}</span>
          </span>
          <span>
            rejected{" "}
            <span className="text-redline">{result.verifier.rejected}</span>
          </span>
          <span>
            needs input{" "}
            <span className="text-signal">{result.verifier.needs_user_input}</span>
          </span>
          <span>
            pages{" "}
            <span className="text-ink">
              {formatNumber(result.estimated_pages_before ?? 0)} →{" "}
              {formatNumber(result.estimated_pages_after ?? 0)}
            </span>
          </span>
          {result.verifier.reasons.length > 0 && (
            <span className="max-w-full normal-case tracking-normal text-muted">
              {result.verifier.reasons.slice(0, 2).join(" · ")}
            </span>
          )}
        </div>

        {result.notes.length > 0 && (
          <div className="border-t border-line bg-signal-soft/40 px-5 py-3">
            {result.notes.map((note) => (
              <p
                key={note}
                className="text-caption leading-relaxed text-ink/80"
              >
                {note}
              </p>
            ))}
          </div>
        )}

        {(result.iteration_history?.length ?? 0) > 0 && (
          <details className="border-t border-line">
            <summary className="cursor-pointer px-5 py-2.5 font-data text-[9px] uppercase tracking-[0.12em] text-muted">
              iteration history · compile + re-score
            </summary>
            <div className="divide-y divide-line border-t border-line">
              {result.iteration_history.map((record) => (
                <div
                  key={record.iteration}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2 font-data text-[9px] uppercase tracking-[0.1em] text-muted"
                >
                  <span>#{record.iteration}</span>
                  <span>
                    {formatNumber(record.baseline_score)} →{" "}
                    {formatNumber(record.candidate_score)}
                  </span>
                  <span
                    className={
                      record.score_delta > 0
                        ? "text-ok"
                        : record.score_delta < 0
                          ? "text-redline"
                          : undefined
                    }
                  >
                    {record.score_delta > 0 ? "+" : ""}
                    {formatNumber(record.score_delta)}
                  </span>
                  <span>compile: {record.compile_status}</span>
                  {record.rolled_back && (
                    <span className="text-redline">rolled back</span>
                  )}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>

      {decisionError && (
        <div className="border border-redline/25 bg-redline-soft p-3">
          <p className="font-data text-[9px] uppercase tracking-[0.12em] text-redline">
            decision not saved
          </p>
          <p className="mt-1 text-caption leading-relaxed text-ink/80">
            {decisionError}
          </p>
        </div>
      )}

      {verified.length > 0 && (
        <div>
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="eyebrow text-muted">verified edits</span>
            <span className="font-data text-[9px] text-muted">
              source-bound · safe to accept or reject
            </span>
          </div>
          <div className="space-y-3">
            {verified.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                proposal={proposal}
                pending={pendingChangeId === proposal.id}
                onDecide={(status, proposed) =>
                  onDecide(proposal.id, status, proposed)
                }
                onEdit={(proposed) => onEdit(proposal.id, proposed)}
              />
            ))}
          </div>
        </div>
      )}

      {questions.length > 0 && (
        <div>
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="eyebrow text-signal">questions, not claims</span>
            <span className="font-data text-[9px] text-muted">
              the engine will not invent missing facts
            </span>
          </div>
          <div className="space-y-3">
            {questions.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                proposal={proposal}
                pending={pendingChangeId === proposal.id}
                onDecide={(status, proposed) =>
                  onDecide(proposal.id, status, proposed)
                }
                onEdit={(proposed) => onEdit(proposal.id, proposed)}
              />
            ))}
          </div>
        </div>
      )}

      {rejectedByVerifier.length > 0 && (
        <div>
          <span className="eyebrow text-redline">discarded by verifier</span>
          <div className="mt-2 space-y-3">
            {rejectedByVerifier.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                proposal={proposal}
                pending={pendingChangeId === proposal.id}
                onDecide={(status, proposed) =>
                  onDecide(proposal.id, status, proposed)
                }
                onEdit={(proposed) => onEdit(proposal.id, proposed)}
              />
            ))}
          </div>
        </div>
      )}

      {result.proposals.length === 0 && (
        <div className="border border-line bg-paper p-5">
          <p className="text-small text-ink">
            No proposals were generated for this resume/JD pair.
          </p>
          <p className="mt-1 text-caption text-muted">
            The deterministic optimiser only proposes changes it can trace to
            your source. A higher score is not guaranteed.
          </p>
        </div>
      )}

      <p className="font-data text-[9px] leading-relaxed text-muted">
        Projected score uses a real re-score of the accepted proposal set. Before
        you decide, it assumes every verified edit is accepted. Accepting a
        reorder may not move the score.
        {result.model_versions.llm_provider === "stub" ? (
          <>
            {" "}
            The LLM is running as a deterministic stub, so no generated rewrite
            is present.
          </>
        ) : (
          <> LLM provider: {result.model_versions.llm_provider}.</>
        )}{" "}
        Verified{" "}
        {percent(
          result.proposals.length
            ? verified.length / result.proposals.length
            : 0,
        )}{" "}
        of proposals.
      </p>
    </section>
  );
}

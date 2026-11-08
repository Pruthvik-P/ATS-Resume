import type { ChangeProposal, ChangeStatus } from "@/lib/api-types";
import { humanize } from "@/lib/format";

const KIND_LABEL: Record<ChangeProposal["kind"], string> = {
  rewrite_bullet: "rewrite bullet",
  reorder_skills: "reorder skills",
  placeholder_metric: "add a metric",
  missing_skill_question: "missing must-have",
  parse_fix: "parse fix",
  summary_tailor: "tailor summary",
};

const TRUTHFULNESS_CLASS: Record<ChangeProposal["truthfulness"], string> = {
  verified: "border-ok/25 bg-ok-soft text-ok",
  needs_user_input: "border-signal/25 bg-signal-soft text-signal",
  rejected: "border-redline/25 bg-redline-soft text-redline",
};

const TRUTHFULNESS_LABEL: Record<ChangeProposal["truthfulness"], string> = {
  verified: "verified against source",
  needs_user_input: "needs your input",
  rejected: "rejected by verifier",
};

const RISK_CLASS: Record<ChangeProposal["risk"], string> = {
  low: "text-muted",
  medium: "text-signal",
  high: "text-redline",
};

function StatusNote({ status }: { status: ChangeStatus }) {
  if (status === "accepted") {
    return <span className="text-ok">✓ included in the re-score</span>;
  }
  if (status === "rejected") {
    return <span className="text-redline">✕ excluded · original kept</span>;
  }
  return null;
}

function DiffPane({
  sign,
  label,
  text,
  tone,
}: {
  sign: string;
  label: string;
  text: string;
  tone: "original" | "proposed";
}) {
  const styles =
    tone === "original"
      ? "border-redline/25 bg-redline-soft/50 text-ink/70"
      : "border-ok/25 bg-ok-soft/50 text-ink";

  return (
    <div className={`border p-3 ${styles}`}>
      <div
        className={`mb-1.5 flex items-center gap-2 font-data text-[9px] uppercase tracking-[0.16em] ${
          tone === "original" ? "text-redline" : "text-ok"
        }`}
      >
        <span aria-hidden="true">{sign}</span>
        {label}
      </div>
      <p className="whitespace-pre-wrap text-caption leading-relaxed">
        {text}
      </p>
    </div>
  );
}

export function ProposalCard({
  proposal,
  pending,
  onDecide,
}: {
  proposal: ChangeProposal;
  pending: boolean;
  onDecide: (status: "accepted" | "rejected") => void;
}) {
  const needsInput = proposal.truthfulness === "needs_user_input";
  const isPlaceholder = proposal.kind === "placeholder_metric";
  const canAccept = proposal.truthfulness === "verified";
  const hasDiff = Boolean(proposal.original || proposal.proposed);

  return (
    <div className="border border-line bg-paper">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2 font-data text-[10px] uppercase tracking-[0.14em] text-muted">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              proposal.truthfulness === "verified"
                ? "bg-ok"
                : proposal.truthfulness === "needs_user_input"
                  ? "bg-signal"
                  : "bg-redline"
            }`}
          />
          optimiser
          <span className="text-line">/</span>
          {KIND_LABEL[proposal.kind]}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`border px-2 py-0.5 font-data text-[9px] font-medium uppercase tracking-[0.1em] ${TRUTHFULNESS_CLASS[proposal.truthfulness]}`}
          >
            {TRUTHFULNESS_LABEL[proposal.truthfulness]}
          </span>
          <span
            className={`font-data text-[9px] uppercase tracking-[0.1em] ${RISK_CLASS[proposal.risk]}`}
          >
            {proposal.risk} risk
          </span>
        </div>
      </div>

      <div className="space-y-3 px-4 py-4 sm:px-5">
        {proposal.kind === "missing_skill_question" && (
          <div className="border border-signal/25 bg-signal-soft/60 p-3">
            <p className="font-data text-[9px] uppercase tracking-[0.14em] text-signal">
              question · not an edit
            </p>
            <p className="mt-1.5 text-caption leading-relaxed text-ink/80">
              {proposal.rationale}
            </p>
          </div>
        )}

        {hasDiff && (
          <div className="space-y-2.5">
            {proposal.original && (
              <DiffPane
                sign="−"
                label="original"
                text={proposal.original}
                tone="original"
              />
            )}
            {proposal.proposed && (
              <DiffPane
                sign="+"
                label={isPlaceholder ? "proposed · placeholder" : "proposed"}
                text={proposal.proposed}
                tone="proposed"
              />
            )}
          </div>
        )}

        {proposal.kind !== "missing_skill_question" && (
          <p className="text-caption leading-relaxed text-muted">
            {proposal.rationale}
          </p>
        )}

        {isPlaceholder && (
          <p className="border-l-2 border-signal pl-3 font-data text-[9px] leading-relaxed text-signal">
            The placeholder must be replaced with a real number. This build has
            no proposal editor yet, so the placeholder cannot be accepted as-is.
          </p>
        )}

        {(proposal.evidence_spans.length > 0 ||
          proposal.jd_keywords_used.length > 0 ||
          proposal.target_ref) && (
          <div className="flex flex-wrap gap-1.5 border-t border-line pt-3">
            {proposal.target_ref && (
              <span className="border border-line bg-bg/60 px-1.5 py-0.5 font-data text-[8px] text-muted">
                source: {proposal.target_ref}
              </span>
            )}
            {proposal.evidence_spans.map((span) => (
              <span
                key={span}
                className="border border-line bg-bg/60 px-1.5 py-0.5 font-data text-[8px] text-muted"
                title="Evidence span from the resume"
              >
                {span}
              </span>
            ))}
            {proposal.jd_keywords_used.map((keyword) => (
              <span
                key={keyword}
                className="border border-accent/20 bg-accent-soft px-1.5 py-0.5 font-data text-[8px] text-accent-strong"
                title="JD keyword used by this proposal"
              >
                {keyword}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3 sm:px-5">
        {proposal.status === "pending" ? (
          <>
            {canAccept ? (
              <button
                type="button"
                onClick={() => onDecide("accepted")}
                disabled={pending}
                className="inline-flex h-8 items-center bg-ok px-3 font-data text-[10px] font-semibold uppercase tracking-[0.1em] text-paper transition-colors hover:bg-ok/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pending ? "Saving…" : "Accept"}
              </button>
            ) : (
              <span className="inline-flex h-8 items-center border border-signal/30 bg-signal-soft px-3 font-data text-[10px] font-semibold uppercase tracking-[0.1em] text-signal">
                {needsInput ? "Your input required" : "Not acceptable as-is"}
              </span>
            )}
            <button
              type="button"
              onClick={() => onDecide("rejected")}
              disabled={pending}
              className="inline-flex h-8 items-center border border-line px-3 font-data text-[10px] font-medium uppercase tracking-[0.1em] text-ink transition-colors hover:bg-bg disabled:cursor-not-allowed disabled:opacity-50"
            >
              {needsInput ? "Dismiss question" : "Reject"}
            </button>
            <span className="ml-auto font-data text-[9px] text-muted">
              you approve every edit
            </span>
          </>
        ) : (
          <>
            <span
              aria-live="polite"
              className="font-data text-[10px]"
            >
              <StatusNote status={proposal.status} />
            </span>
            {canAccept && (
              <button
                type="button"
                onClick={() =>
                  onDecide(
                    proposal.status === "accepted" ? "rejected" : "accepted",
                  )
                }
                disabled={pending}
                className="ml-auto font-data text-[9px] uppercase tracking-[0.1em] text-muted underline underline-offset-4 transition-colors hover:text-ink disabled:opacity-50"
              >
                {pending
                  ? "Saving…"
                  : proposal.status === "accepted"
                    ? "reject instead"
                    : "accept instead"}
              </button>
            )}
          </>
        )}
      </div>

      <div className="border-t border-line bg-bg/50 px-4 py-2.5 sm:px-5">
        <p className="font-data text-[9px] leading-relaxed text-muted">
          section: {humanize(proposal.section)} · no unsupported claim is
          inserted. Missing facts stay questions.
        </p>
      </div>
    </div>
  );
}

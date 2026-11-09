"use client";

import { useState } from "react";
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

const PLACEHOLDER_RE = /\[ADD METRIC:[^\]]*\]/i;

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
      <p className="whitespace-pre-wrap text-caption leading-relaxed">{text}</p>
    </div>
  );
}

export function ProposalCard({
  proposal,
  pending,
  onDecide,
  onEdit,
}: {
  proposal: ChangeProposal;
  pending: boolean;
  onDecide: (status: "accepted" | "rejected", proposed?: string) => void;
  onEdit: (proposed: string) => Promise<void>;
}) {
  const needsInput = proposal.truthfulness === "needs_user_input";
  const isPlaceholder = proposal.kind === "placeholder_metric";
  const isEditable =
    proposal.kind === "rewrite_bullet" || proposal.kind === "placeholder_metric";
  const hasDiff = Boolean(proposal.original || proposal.proposed);

  // A null draft means "show the server value". The draft only becomes local
  // while the user is actively editing, so a saved proposal never goes stale.
  const [draft, setDraft] = useState<string | null>(null);
  const [editing, setEditing] = useState(needsInput && isEditable);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const currentDraft = draft ?? proposal.proposed;
  const hasPlaceholder = PLACEHOLDER_RE.test(currentDraft);
  const dirty = currentDraft.trim() !== proposal.proposed.trim();
  const canAccept =
    proposal.truthfulness === "verified" &&
    !hasPlaceholder &&
    currentDraft.trim().length > 0;

  const saveEdit = async () => {
    if (!currentDraft.trim() || savingEdit) return;
    setSavingEdit(true);
    setEditError(null);
    try {
      await onEdit(currentDraft);
      setDraft(null);
      setEditing(false);
    } catch (error) {
      setEditError(
        error instanceof Error ? error.message : "The edit could not be saved.",
      );
    } finally {
      setSavingEdit(false);
    }
  };

  const accept = () => {
    const proposed = dirty && !hasPlaceholder ? currentDraft : undefined;
    onDecide("accepted", proposed);
  };

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
          {proposal.edited_by_user && (
            <span className="border border-accent/25 bg-accent-soft px-2 py-0.5 font-data text-[9px] font-medium uppercase tracking-[0.1em] text-accent-strong">
              edited by you
            </span>
          )}
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

        {hasDiff && !editing && (
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
                label={
                  isPlaceholder && hasPlaceholder
                    ? "proposed · placeholder"
                    : "proposed"
                }
                text={proposal.proposed}
                tone="proposed"
              />
            )}
          </div>
        )}

        {editing && isEditable && (
          <div className="border border-accent/30 bg-accent-soft/30 p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="font-data text-[9px] uppercase tracking-[0.14em] text-accent-strong">
                edit proposal
              </span>
              <span className="font-data text-[9px] text-muted">
                user-authored text is saved as a confirmed fact
              </span>
            </div>
            <textarea
              value={currentDraft}
              onChange={(event) => setDraft(event.target.value)}
              rows={4}
              aria-label="Edit proposed bullet"
              className="w-full resize-y border border-line bg-paper p-3 text-caption leading-relaxed text-ink outline-none transition-colors focus:border-accent"
            />
            {hasPlaceholder && (
              <p className="mt-2 border-l-2 border-signal pl-3 font-data text-[9px] leading-relaxed text-signal">
                Replace the [ADD METRIC: …] placeholder with a real number before
                accepting. The engine will not invent one.
              </p>
            )}
            {editError && (
              <p className="mt-2 border-l-2 border-redline pl-3 text-caption text-redline">
                {editError}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void saveEdit()}
                disabled={savingEdit || !currentDraft.trim() || !dirty}
                className="inline-flex h-8 items-center bg-accent px-3 font-data text-[10px] font-semibold uppercase tracking-[0.1em] text-brand-ink transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
              >
                {savingEdit ? "Verifying…" : "Save & verify"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft(null);
                  setEditError(null);
                  setEditing(false);
                }}
                disabled={savingEdit}
                className="inline-flex h-8 items-center border border-line px-3 font-data text-[10px] font-medium uppercase tracking-[0.1em] text-ink transition-colors hover:bg-bg disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {proposal.kind !== "missing_skill_question" && (
          <p className="text-caption leading-relaxed text-muted">
            {proposal.rationale}
          </p>
        )}

        {(proposal.verification_notes?.length ?? 0) > 0 && (
          <div className="border-l-2 border-signal/60 pl-3">
            {proposal.verification_notes?.map((note) => (
              <p
                key={note}
                className="font-data text-[9px] leading-relaxed text-signal"
              >
                verifier: {note}
              </p>
            ))}
          </div>
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
                onClick={accept}
                disabled={pending || savingEdit}
                className="inline-flex h-8 items-center bg-ok px-3 font-data text-[10px] font-semibold uppercase tracking-[0.1em] text-paper transition-colors hover:bg-ok/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pending ? "Saving…" : dirty ? "Accept with edit" : "Accept"}
              </button>
            ) : (
              <span className="inline-flex h-8 items-center border border-signal/30 bg-signal-soft px-3 font-data text-[10px] font-semibold uppercase tracking-[0.1em] text-signal">
                {needsInput ? "Your input required" : "Not acceptable as-is"}
              </span>
            )}
            {isEditable && !editing && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                disabled={pending || savingEdit}
                className="inline-flex h-8 items-center border border-accent/30 bg-accent-soft/50 px-3 font-data text-[10px] font-medium uppercase tracking-[0.1em] text-accent-strong transition-colors hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isPlaceholder ? "Fill in metric" : "Edit wording"}
              </button>
            )}
            <button
              type="button"
              onClick={() => onDecide("rejected")}
              disabled={pending || savingEdit}
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
            <span aria-live="polite" className="font-data text-[10px]">
              <StatusNote status={proposal.status} />
            </span>
            <button
              type="button"
              onClick={() =>
                onDecide(proposal.status === "accepted" ? "rejected" : "accepted")
              }
              disabled={pending}
              className="ml-auto font-data text-[9px] uppercase tracking-[0.1em] text-muted underline underline-offset-4 transition-colors hover:text-ink disabled:opacity-50"
            >
              {pending
                ? "Saving…"
                : proposal.status === "accepted"
                  ? "reject instead · undo"
                  : "accept instead"}
            </button>
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

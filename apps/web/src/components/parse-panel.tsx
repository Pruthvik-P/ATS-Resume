import type { ResumeRead, ScoreReport, Severity } from "@/lib/api-types";
import { asStringArray, plural } from "@/lib/format";

const SEVERITY_CLASS: Record<Severity, string> = {
  error: "border-redline/25 bg-redline-soft text-redline",
  warning: "border-signal/25 bg-signal-soft text-signal",
  info: "border-line bg-bg text-muted",
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-paper px-3 py-2.5">
      <p className="font-data text-[8px] uppercase tracking-[0.14em] text-muted">
        {label}
      </p>
      <p className="mt-1 truncate text-caption font-semibold text-ink" title={value}>
        {value}
      </p>
    </div>
  );
}

export function ParsePanel({
  resume,
  report,
}: {
  resume: ResumeRead;
  report: ScoreReport;
}) {
  const document = resume.document;
  const basics = document.canonical.basics;
  const issues = document.issues;
  const missingFields = asStringArray(report.parse_fidelity.missing_fields);
  const errors = issues.filter((issue) => issue.severity === "error").length;

  return (
    <section className="border border-line bg-paper">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex items-center gap-2">
          <span
            className={`h-1.5 w-1.5 rounded-full ${errors ? "bg-redline" : issues.length ? "bg-signal" : "bg-ok"}`}
          />
          <span className="eyebrow text-muted">parse / source</span>
        </div>
        <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
          {document.format.toUpperCase()} · {resume.filename}
        </span>
      </div>

      <div className="grid gap-px border-b border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="parsed name" value={basics.name ?? "not detected"} />
        <Stat label="email" value={basics.email ?? "not detected"} />
        <Stat
          label="roles / skills"
          value={`${document.canonical.work.length} / ${document.canonical.skills.length}`}
        />
        <Stat
          label="structuring"
          value={`${document.structuring.method} · ${document.structuring.confidence.toFixed(2)}`}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.08fr_0.92fr]">
        <div className="p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="eyebrow text-muted">extraction issues</span>
            <span className="font-data text-[9px] text-muted">
              {plural(issues.length, "issue")}
            </span>
          </div>

          {issues.length === 0 ? (
            <p className="mt-3 border border-ok/25 bg-ok-soft/60 p-3 text-caption leading-relaxed text-ink/80">
              No extraction problems were reported for this document. That does
              not guarantee every ATS vendor will read it the same way.
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {issues.map((issue, index) => (
                <li
                  key={`${issue.code}-${index}`}
                  className="border border-line p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`border px-1.5 py-0.5 font-data text-[8px] uppercase tracking-[0.12em] ${SEVERITY_CLASS[issue.severity]}`}
                    >
                      {issue.severity}
                    </span>
                    <span className="font-data text-[9px] uppercase tracking-[0.1em] text-muted">
                      {issue.code}
                    </span>
                    {issue.auto_fixable && (
                      <span className="font-data text-[8px] uppercase tracking-[0.1em] text-accent">
                        auto-fixable
                      </span>
                    )}
                    {issue.source_ref?.line ? (
                      <span className="ml-auto font-data text-[9px] text-muted">
                        line {issue.source_ref.line}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1.5 text-caption leading-relaxed text-ink/80">
                    {issue.message}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border-t border-line p-5 sm:p-6 lg:border-l lg:border-t-0">
          <span className="eyebrow text-muted">field recall</span>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-3xl font-bold leading-none text-ink">
              {report.parse_fidelity.field_recall.toFixed(0)}%
            </span>
            <span className="font-data text-[9px] uppercase tracking-[0.14em] text-muted">
              of checked fields recovered
            </span>
          </div>

          <div className="mt-4">
            <p className="font-data text-[9px] uppercase tracking-[0.14em] text-muted">
              missing fields
            </p>
            {missingFields.length === 0 ? (
              <p className="mt-1.5 text-caption text-muted">
                None of the checked fields were missing.
              </p>
            ) : (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {missingFields.map((field) => (
                  <span
                    key={field}
                    className="border border-redline/25 bg-redline-soft/60 px-1.5 py-0.5 font-data text-[9px] text-redline"
                  >
                    {field}
                  </span>
                ))}
              </div>
            )}
          </div>

          <p className="mt-5 border-t border-line pt-3 text-caption leading-relaxed text-muted">
            Parse fidelity is measured against the text this engine extracted.
            Different ATS vendors may extract differently. PDF text is read with
            pypdf (or PyMuPDF when installed); OCR is not enabled. LaTeX is read
            as source text, not compiled.
          </p>
        </div>
      </div>
    </section>
  );
}

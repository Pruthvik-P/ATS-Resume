import type { JDAnalysisResponse } from "@/lib/api-types";
import { humanize, plural } from "@/lib/format";

function RequirementChip({
  skill,
  importance,
}: {
  skill: string;
  importance: "must" | "nice";
}) {
  return (
    <span
      className={`border px-2 py-1 font-data text-[10px] ${
        importance === "must"
          ? "border-accent/25 bg-accent-soft text-accent-strong"
          : "border-line bg-bg/60 text-ink"
      }`}
    >
      {skill}
    </span>
  );
}

export function JdPanel({ jd }: { jd: JDAnalysisResponse }) {
  const analysis = jd.analysis;
  const title = analysis.title ?? "Untitled role";
  const years =
    analysis.years_min && analysis.years_max
      ? `${analysis.years_min}–${analysis.years_max} years`
      : analysis.years_min
        ? `${analysis.years_min}+ years`
        : null;

  return (
    <section className="border border-line bg-paper">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line p-5 sm:p-6">
        <div>
          <span className="eyebrow text-muted">job / analysis</span>
          <h3 className="mt-2 text-h3 text-ink">{title}</h3>
          <p className="mt-1 font-data text-[10px] uppercase tracking-[0.12em] text-muted">
            {[analysis.company, analysis.seniority, years]
              .filter(Boolean)
              .join(" · ") || "no company or seniority stated"}
          </p>
        </div>
        <div className="text-right font-data text-[9px] leading-relaxed text-muted">
          <p>
            {plural(analysis.must_have.length, "must-have")} ·{" "}
            {plural(analysis.nice_to_have.length, "nice-to-have")}
          </p>
          <p>{analysis.analyser_version}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="p-5 sm:p-6">
          <div>
            <div className="flex items-center justify-between gap-3">
              <span className="eyebrow text-muted">must-have</span>
              <span className="font-data text-[9px] text-muted">
                weighted 2× in keyword match
              </span>
            </div>
            {analysis.must_have.length === 0 ? (
              <p className="mt-2 text-caption text-muted">
                No hard must-have skills were extracted.
              </p>
            ) : (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {analysis.must_have.map((item) => (
                  <RequirementChip
                    key={item.canonical}
                    skill={item.skill}
                    importance="must"
                  />
                ))}
              </div>
            )}
          </div>

          <div className="mt-5">
            <span className="eyebrow text-muted">nice-to-have</span>
            {analysis.nice_to_have.length === 0 ? (
              <p className="mt-2 text-caption text-muted">
                No nice-to-have skills were extracted.
              </p>
            ) : (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {analysis.nice_to_have.map((item) => (
                  <RequirementChip
                    key={item.canonical}
                    skill={item.skill}
                    importance="nice"
                  />
                ))}
              </div>
            )}
          </div>

          {analysis.responsibilities.length > 0 && (
            <div className="mt-5 border-t border-line pt-4">
              <span className="eyebrow text-muted">responsibilities</span>
              <ul className="mt-2 space-y-1.5">
                {analysis.responsibilities.slice(0, 5).map((item) => (
                  <li
                    key={item}
                    className="flex gap-2 text-caption leading-relaxed text-ink/80"
                  >
                    <span className="text-accent">↳</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="border-t border-line p-5 sm:p-6 lg:border-l lg:border-t-0">
          <div className="flex items-center justify-between gap-3">
            <span className="eyebrow text-muted">knock-outs</span>
            <span className="font-data text-[9px] text-muted">
              not verifiable by the engine
            </span>
          </div>
          {analysis.knockouts.length === 0 ? (
            <p className="mt-2 text-caption text-muted">
              No eligibility or knock-out language was detected.
            </p>
          ) : (
            <ul className="mt-2 space-y-2">
              {analysis.knockouts.map((knockout) => (
                <li
                  key={`${knockout.kind}-${knockout.text}`}
                  className="border border-signal/25 bg-signal-soft/50 p-3"
                >
                  <p className="font-data text-[9px] uppercase tracking-[0.12em] text-signal">
                    {humanize(knockout.kind)}
                    {knockout.hard ? " · hard" : ""}
                  </p>
                  <p className="mt-1 text-caption leading-relaxed text-ink/80">
                    {knockout.text}
                  </p>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 font-data text-[9px] leading-relaxed text-muted">
            Confirm work authorization, location, clearance, and degree claims
            yourself. The score cannot verify them.
          </p>

          {jd.warnings.length > 0 && (
            <div className="mt-4 border-t border-line pt-3">
              <p className="font-data text-[9px] uppercase tracking-[0.14em] text-signal">
                analysis warnings
              </p>
              <ul className="mt-1.5 space-y-1">
                {jd.warnings.map((warning) => (
                  <li
                    key={warning}
                    className="text-[10px] leading-relaxed text-muted"
                  >
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

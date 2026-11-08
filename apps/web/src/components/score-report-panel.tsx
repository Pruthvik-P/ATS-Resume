import type {
  ComponentScore,
  Recommendation,
  ScoreKey,
  ScoreReport,
} from "@/lib/api-types";
import {
  asNumber,
  asStringArray,
  formatNumber,
  humanize,
  percent,
  plural,
  scoreBarClass,
  scoreTextClass,
} from "@/lib/format";

const COMPONENTS: Array<{
  key: ScoreKey;
  label: string;
  detail: (component: ComponentScore) => string;
}> = [
  {
    key: "keyword_match",
    label: "Hard-skill / keyword match",
    detail: (component) => {
      const matched = asStringArray(component.matched);
      const missingMust = asStringArray(component.missing_must_have);
      const considered = asNumber(component.requirements_considered);
      const base = considered
        ? `Matched ${matched.length} of ${considered} JD requirements.`
        : "No JD skill requirements were identified.";
      return missingMust.length
        ? `${base} Missing must-have: ${missingMust.join(", ")}.`
        : base;
    },
  },
  {
    key: "semantic_relevance",
    label: "Semantic relevance",
    detail: (component) => {
      const requirements = asNumber(component.requirements);
      const unmatched = asStringArray(component.unmatched_requirements);
      const calibration = component.calibration as
        | { embedding?: string }
        | undefined;
      const note = calibration?.embedding
        ? ` Embedding: ${calibration.embedding}.`
        : "";
      return requirements
        ? `${plural(requirements, "JD responsibility", "JD responsibilities")} compared; ${unmatched.length} had no close evidence match.${note}`
        : `No responsibilities were available to compare.${note}`;
    },
  },
  {
    key: "experience_fit",
    label: "Experience & seniority fit",
    detail: (component) => {
      const years = asNumber(component.total_years);
      const required = asNumber(component.required_years_min);
      const roles = asNumber(component.roles);
      const seniority = component.seniority_detected;
      const roleText = roles ? plural(roles, "dated role") : "no dated roles";
      const requiredText = required ? ` against ${required} required` : "";
      return `${formatNumber(years)} years detected${requiredText}; ${roleText}; seniority ${String(seniority ?? "unknown")}.`;
    },
  },
  {
    key: "parseability",
    label: "ATS parseability",
    detail: (component) => {
      const recall = asNumber(component.field_recall);
      const missing = asStringArray(component.missing_fields);
      return `Field recall ${formatNumber(recall)}%. ${missing.length ? `Missing parsed fields: ${missing.join(", ")}.` : "All checked fields were recoverable from the extracted text."}`;
    },
  },
  {
    key: "impact",
    label: "Impact & bullet quality",
    detail: (component) => {
      const bullets = asNumber(component.bullets);
      const ratio = asNumber(component.quantification_ratio);
      const weak = Array.isArray(component.weak_bullets)
        ? component.weak_bullets.length
        : 0;
      return `${plural(bullets, "bullet")} assessed; ${percent(ratio)} contain a metric; ${weak} read as weak.`;
    },
  },
  {
    key: "education",
    label: "Education & certifications",
    detail: (component) => {
      const level = asNumber(component.degree_level);
      const certifications = asNumber(component.certifications);
      const notes = asStringArray(component.notes);
      return `Degree level ${level}/5; ${plural(certifications, "certification")}.${notes.length ? ` ${notes[0]}` : ""}`;
    },
  },
  {
    key: "readability",
    label: "Readability & language",
    detail: (component) => {
      const flesch = asNumber(component.flesch_reading_ease);
      const avgWords = asNumber(component.avg_words_per_sentence);
      const actionStarts = asNumber(component.action_start_ratio);
      return `Flesch ${formatNumber(flesch)}; ${formatNumber(avgWords)} words per sentence; ${percent(actionStarts)} of bullets start with an action verb.`;
    },
  },
];

const PRIORITY_CLASS: Record<Recommendation["priority"], string> = {
  high: "border-redline/25 bg-redline-soft text-redline",
  medium: "border-signal/25 bg-signal-soft text-signal",
  low: "border-line bg-bg text-muted",
};

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="bg-paper px-4 py-3">
      <p className="font-data text-[9px] uppercase tracking-[0.14em] text-muted">
        {label}
      </p>
      <p className="mt-1 font-display text-lg font-semibold leading-none text-ink">
        {value}
      </p>
      {hint && (
        <p className="mt-1 font-data text-[9px] leading-relaxed text-muted">
          {hint}
        </p>
      )}
    </div>
  );
}

export function ScoreReportPanel({ report }: { report: ScoreReport }) {
  const capped =
    report.caps.length > 0 ||
    report.penalties.length > 0 ||
    report.knockouts.length > 0;

  return (
    <section className="border border-line bg-paper">
      <div className="flex flex-col gap-6 border-b border-line p-5 sm:p-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <span className="eyebrow text-muted">score / report</span>
          <div className="mt-3 flex items-baseline gap-3">
            <span
              className={`font-display text-[4.2rem] font-bold leading-[0.85] tracking-[-0.05em] ${scoreTextClass(report.overall_score)}`}
            >
              {formatNumber(report.overall_score)}
            </span>
            <span className="font-data text-[10px] uppercase leading-relaxed tracking-[0.16em] text-muted">
              / 100
              <br />
              calibrated proxy
            </span>
          </div>
          <p className="mt-3 max-w-xl text-small leading-relaxed text-ink">
            {report.grade}
          </p>
          <p className="mt-1 max-w-xl text-caption leading-relaxed text-muted">
            Not ground truth. The raw component score was{" "}
            <span className="text-ink">{formatNumber(report.raw_score)}</span>
            {report.caps.length > 0 ? ", then capped." : "."}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3 lg:min-w-[22rem]">
          <Metric label="raw score" value={formatNumber(report.raw_score)} />
          <Metric
            label="parse fidelity"
            value={formatNumber(report.parse_fidelity.score)}
            hint={`${formatNumber(report.parse_fidelity.field_recall)}% field recall`}
          />
          <Metric
            label="caps"
            value={String(report.caps.length)}
            hint={report.caps.length ? "score limited" : "none applied"}
          />
          <Metric
            label="penalties"
            value={formatNumber(
              report.penalties.reduce((total, item) => total + item.points, 0),
            )}
            hint="points removed"
          />
          <Metric
            label="must-have gaps"
            value={String(
              asStringArray(report.breakdown.keyword_match?.missing_must_have)
                .length,
            )}
            hint="hard requirements"
          />
          <Metric
            label="scoring model"
            value={report.scoring_version}
            hint={report.model_versions.embedding ?? "deterministic"}
          />
        </div>
      </div>

      {capped && (
        <div className="border-b border-line bg-bg/50 p-5 sm:p-6">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-redline" />
            <span className="eyebrow text-redline">why the number is limited</span>
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {report.caps.map((cap) => (
              <div
                key={`${cap.code}-${cap.reason}`}
                className="border border-redline/20 bg-redline-soft/50 p-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-data text-[9px] uppercase tracking-[0.14em] text-redline">
                    cap · {humanize(cap.code)}
                  </span>
                  <span className="font-data text-[10px] font-semibold text-redline">
                    {formatNumber(cap.cap)}
                  </span>
                </div>
                <p className="mt-1.5 text-caption leading-relaxed text-ink/80">
                  {cap.reason}
                </p>
              </div>
            ))}
            {report.penalties.map((penalty, index) => (
              <div
                key={`${penalty.code}-${index}`}
                className="border border-signal/25 bg-signal-soft/60 p-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-data text-[9px] uppercase tracking-[0.14em] text-signal">
                    penalty · {humanize(penalty.code)}
                  </span>
                  <span className="font-data text-[10px] font-semibold text-signal">
                    −{formatNumber(penalty.points)}
                  </span>
                </div>
                <p className="mt-1.5 text-caption leading-relaxed text-ink/80">
                  {penalty.reason}
                </p>
              </div>
            ))}
          </div>
          {report.knockouts.length > 0 && (
            <ul className="mt-4 space-y-1.5 border-t border-line pt-3">
              {report.knockouts.map((knockout) => (
                <li
                  key={knockout}
                  className="flex gap-2 font-data text-[10px] leading-relaxed text-ink/80"
                >
                  <span className="text-redline">↳</span>
                  {knockout}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1.08fr_0.92fr]">
        <div className="p-5 sm:p-6">
          <div className="mb-3 flex items-center justify-between font-data text-[10px] uppercase tracking-[0.16em] text-muted">
            <span>component</span>
            <span>score · weight</span>
          </div>
          <ul className="border-y border-line">
            {COMPONENTS.map(({ key, label, detail }, index) => {
              const component = report.breakdown[key];
              if (!component) return null;
              const weight = component.weight * 100;
              return (
                <li key={key} className="border-b border-line py-4 last:border-0">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-small font-medium text-ink">{label}</p>
                      <p className="mt-1 max-w-md text-caption leading-relaxed text-muted">
                        {detail(component)}
                      </p>
                    </div>
                    <span className="shrink-0 font-data text-caption text-muted">
                      <span className="text-ink">
                        {formatNumber(component.score)}
                      </span>
                      <span className="mx-1 text-line">·</span>
                      {formatNumber(weight)}%
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden bg-line/70">
                    <span
                      className={`bar-fill block h-full ${scoreBarClass(component.score)}`}
                      style={{
                        width: `${Math.max(0, Math.min(100, component.score))}%`,
                        animationDelay: `${120 + index * 55}ms`,
                      }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 font-data text-[9px] leading-relaxed text-muted">
            Weights are returned with every report. Must-haves count double in
            keyword matching; a skills-list mention without bullet evidence is
            discounted. Semantic scoring uses a deterministic hashed n-gram
            embedder, not a trained model.
          </p>
        </div>

        <div className="border-t border-line p-5 sm:p-6 lg:border-l lg:border-t-0">
          <span className="eyebrow text-muted">recommendations</span>
          {report.recommendations.length === 0 ? (
            <p className="mt-3 text-small leading-relaxed text-muted">
              No specific recommendations were generated for this pair.
            </p>
          ) : (
            <ul className="mt-3 space-y-3">
              {report.recommendations.map((recommendation, index) => (
                <li
                  key={`${recommendation.priority}-${recommendation.type}-${index}`}
                  className="border border-line bg-paper p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`border px-1.5 py-0.5 font-data text-[9px] uppercase tracking-[0.12em] ${PRIORITY_CLASS[recommendation.priority]}`}
                    >
                      {recommendation.priority}
                    </span>
                    <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                      {humanize(recommendation.type)}
                    </span>
                  </div>
                  <p className="mt-2 text-caption leading-relaxed text-ink/80">
                    {recommendation.text}
                  </p>
                  {recommendation.evidence.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {recommendation.evidence.slice(0, 5).map((item) => (
                        <span
                          key={item}
                          className="border border-line bg-bg/60 px-1.5 py-0.5 font-data text-[8px] text-muted"
                        >
                          {item}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          <div className="mt-5 border-t border-line pt-3 font-data text-[9px] leading-relaxed text-muted">
            <p>
              engine: {report.model_versions.scoring ?? "scoring-v1"} · embedder:{" "}
              {report.model_versions.embedding ?? "unknown"}
            </p>
            <p>
              structuring: {report.model_versions.structuring ?? "unknown"} · JD
              analyser: {report.model_versions.jd_analyser ?? "unknown"}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

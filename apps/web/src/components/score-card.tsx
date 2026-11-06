export type ScoreBreakdown = {
  overall: number;
  grade: string;
  breakdown: Array<{
    name: string;
    score: number;
    weight: number;
    detail?: string;
  }>;
  knockouts: string[];
  recommendations: Array<{
    priority: "high" | "medium" | "low";
    type: string;
    text: string;
  }>;
};

export function ScoreCard({ report }: { report: ScoreBreakdown }) {
  const colorFor = (score: number) => {
    if (score >= 80) return "text-ok bg-ok/10 border-ok/20";
    if (score >= 60) return "text-amber-700 bg-amber-50 border-amber-200";
    return "text-danger bg-danger/10 border-danger/20";
  };

  return (
    <section className="max-w-4xl mx-auto px-6 py-16">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-10">
        <div>
          <h2 className="text-h2 text-ink">Score report</h2>
          <p className="mt-2 text-small text-muted">
            A calibrated proxy, not ground truth — different ATSs parse and rank
            differently. Use it to find and fix real gaps.
          </p>
        </div>
        <div className="flex items-end gap-4">
          <span className="font-display text-[clamp(3rem,8vw,5.5rem)] font-bold text-ink tracking-tight leading-none">
            {report.overall}
          </span>
          <span className={`text-h3 font-body ${colorFor(report.overall)}`}>
            {report.grade}
          </span>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Overall score bar (left column spans 2 on lg) */}
        <div className="lg:col-span-2">
          <div className="flex items-baseline gap-3 mb-3">
            <span className="text-h3 font-body text-ink">Overall match</span>
            <span className={`text-small font-data ${colorFor(report.overall)}`}>
              {report.overall}%
            </span>
          </div>
          <div className="w-full bg-line rounded-full h-3 overflow-hidden mb-6">
            <div
              className={`h-full ${colorFor(report.overall)}`}
              style={{ width: `${Math.min(report.overall, 100)}%` }}
            />
          </div>
          <p className="text-caption text-muted">
            Weighted across seven scored components — keyword match, semantic
            relevance, experience fit, ATS parseability, bullet impact,
            education, and readability.
          </p>
        </div>

        {/* Knockouts (right column) */}
        {report.knockouts.length > 0 && (
          <div className="lg:col-span-1 bg-danger/5 border border-danger/20 rounded-lg p-5">
            <h4 className="text-small font-body text-danger mb-3 flex items-center gap-2">
              <span aria-hidden="true">⚠</span>
              Knock-outs
            </h4>
            <ul className="text-caption text-ink space-y-2 list-disc list-inside">
              {report.knockouts.map((k, i) => (
                <li key={i}>{k}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Breakdown */}
      <div className="mt-12">
        <h3 className="text-h3 text-ink mb-6">Breakdown</h3>
        <div className="overflow-hidden rounded-lg border border-line bg-paper">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-line">
                <th
                  className="h-11 px-5 py-3 text-caption font-body text-muted uppercase tracking-wider"
                >
                  Component
                </th>
                <th
                  className="h-11 px-5 py-3 text-caption font-body text-muted uppercase tracking-wider text-right"
                >
                  Score
                </th>
                <th
                  className="h-11 px-5 py-3 text-caption font-body text-muted uppercase tracking-wider text-right w-16"
                >
                  Weight
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {report.breakdown.map((b, i) => {
                return (
                  <tr key={i} className="hover:bg-accent-soft/30 transition-colors">
                    <td className="px-5 py-4 text-body text-ink font-body">
                      {b.name}{b.detail && (
                        <span className="ml-2 text-caption text-muted">
                          ({b.detail})
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-small font-data text-right">
                      {b.score}
                    </td>
                    <td className="px-5 py-4 text-small font-data text-right text-muted">
                      {b.weight}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recommendations */}
      {report.recommendations.length > 0 && (
        <div className="mt-12">
          <h3 className="text-h3 text-ink mb-6">Recommended changes</h3>
          <div className="space-y-3">
            {report.recommendations.map((r, i) => (
              <div
                key={i}
                className={`flex gap-3 rounded-lg border p-4 ${
                  r.priority === "high"
                    ? "border-danger/20 bg-danger/5"
                    : "border-line/50 bg-paper"
                }`}
              >
                <span
                  className={`text-caption font-data font-bold ${
                    r.priority === "high"
                      ? "text-danger"
                      : "text-muted"
                  }`}
                >
                  {r.priority}
                </span>
                <p className="text-small text-ink leading-relaxed">{r.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

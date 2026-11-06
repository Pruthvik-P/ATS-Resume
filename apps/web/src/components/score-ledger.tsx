const components = [
  { name: "Hard-skill / keyword match", score: 72, weight: 30 },
  { name: "Semantic relevance", score: 80, weight: 20 },
  { name: "Experience & seniority fit", score: 85, weight: 15 },
  { name: "ATS parseability", score: 90, weight: 15 },
  { name: "Impact & bullet quality", score: 65, weight: 10 },
  { name: "Education & certifications", score: 100, weight: 5 },
  { name: "Readability & language", score: 88, weight: 5 },
];

function scoreColor(score: number) {
  if (score >= 80) return "bg-ok";
  if (score >= 70) return "bg-signal";
  return "bg-redline";
}

export function ScoreLedger() {
  return (
    <section id="scoring" className="scroll-mt-20 border-b border-line bg-paper">
      <div className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[0.82fr_1.18fr] lg:gap-20">
          <div>
            <span className="eyebrow text-muted">the ledger</span>
            <h2 className="text-h2 mt-4 text-ink">
              Seven components.
              <br />
              One honest number.
            </h2>
            <p className="mt-5 max-w-md text-small leading-relaxed text-muted">
              ATS vendors don&apos;t publish their rankings, and there is no
              universal ATS score. So we don&apos;t pretend to give you one. We
              give you a weighted, explainable proxy — and show every input that
              produced it.
            </p>

            <div className="mt-8 flex items-baseline gap-3 border-l-2 border-accent pl-4">
              <span className="font-display text-[3.5rem] font-bold leading-none tracking-[-0.04em] text-ink">
                78
              </span>
              <span className="font-data text-[10px] uppercase leading-relaxed tracking-[0.16em] text-muted">
                / 100
                <br />
                calibrated proxy
              </span>
            </div>

            <p className="mt-4 max-w-sm text-caption leading-relaxed text-muted">
              Not ground truth. Use it to find and fix real gaps, not to chase a
              number.
            </p>

            <div className="mt-8 border border-line bg-bg/60 p-4">
              <p className="eyebrow text-redline">published caps</p>
              <div className="mt-3 space-y-2 font-data text-[10px] leading-relaxed text-ink">
                <p className="flex justify-between gap-4 border-b border-line/70 pb-2">
                  <span>Missing a must-have</span>
                  <span className="text-redline">cap 70</span>
                </p>
                <p className="flex justify-between gap-4 border-b border-line/70 pb-2">
                  <span>Parse fidelity &lt; 60</span>
                  <span className="text-redline">cap 60</span>
                </p>
                <p className="flex justify-between gap-4">
                  <span>Hidden text or stuffing</span>
                  <span className="text-redline">penalty</span>
                </p>
              </div>
            </div>
          </div>

          <div className="self-start">
            <div className="mb-2 flex items-center justify-between font-data text-[10px] uppercase tracking-[0.16em] text-muted">
              <span>component</span>
              <span>score · weight</span>
            </div>
            <ul className="border-y border-line">
              {components.map((component, index) => (
                <li
                  key={component.name}
                  className="group border-b border-line py-4 last:border-0"
                >
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-small text-ink transition-colors group-hover:text-accent">
                      {component.name}
                    </span>
                    <span className="shrink-0 font-data text-caption text-muted">
                      <span className="text-ink">{component.score}</span>
                      <span className="mx-1 text-line">·</span>
                      {component.weight}%
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden bg-line/70">
                    <span
                      className={`bar-fill block h-full ${scoreColor(
                        component.score,
                      )}`}
                      style={{
                        width: `${component.score}%`,
                        animationDelay: `${120 + index * 55}ms`,
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-4 font-data text-[10px] leading-relaxed text-muted">
              Evidence in an experience bullet outscores a bare skills-list
              mention. Must-have requirements carry double weight.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

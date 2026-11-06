import { ChangeCard } from "@/components/change-card";

const rules = [
  {
    label: "source-bound",
    title: "Every claim maps to a line.",
    body: "The rewriter may only draw from your resume and your confirmed facts bank.",
  },
  {
    label: "metric-safe",
    title: "No invented numbers.",
    body: "When a metric would help but isn't there, it inserts a placeholder and asks you.",
  },
  {
    label: "fail-closed",
    title: "Unsupported edits are discarded.",
    body: "Not softened, not paraphrased into something plausible. Thrown away.",
  },
  {
    label: "human-in-the-loop",
    title: "Nothing auto-submits.",
    body: "You accept or reject each change. The final click is always yours.",
  },
];

export function Guardrails() {
  return (
    <section
      id="guardrails"
      className="scroll-mt-20 border-b border-line bg-paper"
    >
      <div className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[1fr_0.92fr] lg:gap-16">
          <div>
            <span className="eyebrow text-muted">the optimiser</span>
            <h2 className="text-h2 mt-4 text-ink">
              It rewrites.
              <br />
              It doesn&apos;t invent.
            </h2>
            <p className="mt-5 max-w-lg text-small leading-relaxed text-muted">
              Most resume tools optimise for a number. This one optimises for a
              resume you can defend in the interview. The verifier checks every
              claim against your source and your confirmed facts — and fails
              closed.
            </p>

            <div className="mt-9 grid gap-px border border-line bg-line sm:grid-cols-2">
              {rules.map((rule) => (
                <div key={rule.label} className="bg-paper p-4">
                  <p className="font-data text-[9px] uppercase tracking-[0.16em] text-accent">
                    {rule.label}
                  </p>
                  <h3 className="mt-2 text-small font-semibold text-ink">
                    {rule.title}
                  </h3>
                  <p className="mt-1.5 text-caption leading-relaxed text-muted">
                    {rule.body}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-6 border-l-2 border-accent pl-4">
              <p className="font-data text-[10px] leading-relaxed text-muted">
                <span className="text-ok">pass</span> — claim traceable to source
                <br />
                <span className="text-redline">fail</span> — unsupported claim is
                discarded, not softened
              </p>
            </div>
          </div>

          <div className="self-start lg:pt-4">
            <ChangeCard />
            <p className="mt-3 font-data text-[9px] leading-relaxed text-muted">
              Interactive preview. Accept or reject the edit — nothing leaves
              this page.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

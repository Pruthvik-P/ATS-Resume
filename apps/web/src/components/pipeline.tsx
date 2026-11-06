const stages = [
  { n: "01", title: "Upload", body: "PDF · DOCX · LaTeX (.tex / .zip)" },
  { n: "02", title: "Parse", body: "to JSON Resume, with a source map" },
  { n: "03", title: "Analyse the JD", body: "must-have vs. nice-to-have" },
  { n: "04", title: "Score", body: "7 weighted, explainable components" },
  { n: "05", title: "Rewrite", body: "grounded in your facts bank" },
  { n: "06", title: "Diff & export", body: "accept each change, then PDF + .tex" },
];

export function Pipeline() {
  return (
    <section id="how-it-works" className="scroll-mt-16 border-b border-line bg-paper">
      <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-20">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <span className="font-data text-[10px] uppercase tracking-[0.2em] text-muted">
              the pipeline
            </span>
            <h2 className="text-h2 mt-2 text-ink">One pass, six steps.</h2>
          </div>
          <p className="max-w-sm text-small text-muted">
            Each step is a real, ordered stage — not a marketing bullet. The
            score you see comes out the other end.
          </p>
        </div>

        <ol className="mt-10 grid gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {stages.map((s) => (
            <li key={s.n} className="bg-paper p-5">
              <div className="flex items-baseline gap-3">
                <span className="font-data text-caption text-accent">{s.n}</span>
                <h3 className="font-body text-small font-semibold text-ink">
                  {s.title}
                </h3>
              </div>
              <p className="mt-2 pl-8 font-data text-caption leading-relaxed text-muted">
                {s.body}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

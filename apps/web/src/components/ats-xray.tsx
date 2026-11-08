const humanLines = [
  "Jane A. Developer",
  "Senior Software Engineer — jane@example.com · (555) 123-4567",
  "linkedin.com/in/janedev",
  "",
  "EXPERIENCE",
  "Staff Engineer — Acme Corp · 2020–Present",
  "• Led a team of 6 to migrate the monolith to AWS,",
  "  cutting deploy time by 40%.",
  "• Designed CI/CD pipelines with GitHub Actions and Terraform.",
  "",
  "EDUCATION",
  "M.S. Computer Science — Tech University · 2020",
];

const machineLines: Array<{ text: string; issue?: string }> = [
  { text: "Jane A. Developer" },
  { text: "Senior Software Engineer — jane@example.com · (555) 123-4567" },
  { text: "linkedin.com/in/janedev" },
  { text: "" },
  { text: "EXPERIENCE" },
  { text: "Staff Engineer — Acme Corp · 2020–Present" },
  { text: "• Led a team of 6 to migrate the monolith to AWS," },
  { text: "  cutting deploy time by 40%." },
  { text: "• Designed CI/CD pipelines with GitHub Actions and Terraform." },
  { text: "" },
  { text: "EDUCATION" },
  { text: "M.S. Computer Science — Tech University · 2020" },
  {
    text: "P y t h o n   ·   A W S",
    issue: "spaced-out letters — icon font not extractable",
  },
  {
    text: "ﬁnance  ﬂow  ﬃ",
    issue: "ligature glyphs returned instead of 'fi' / 'fl'",
  },
  {
    text: "Skills  [IMAGE — 0 chars extracted]",
    issue: "section is an image; the ATS sees nothing",
  },
];

export function AtsXRay() {
  return (
    <section
      id="xray"
      className="scroll-mt-20 border-b border-white/10 bg-ink text-paper"
    >
      <div className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_0.8fr] lg:items-end">
          <div className="max-w-2xl">
            <span className="eyebrow text-slate-500">
              signature / the x-ray
            </span>
            <h2 className="text-h2 mt-4 text-paper">
              What you see vs.
              <br />
              what the ATS sees.
            </h2>
          </div>
          <p className="max-w-md text-small leading-relaxed text-slate-400 lg:justify-self-end">
            LaTeX PDFs can break parsing through ligatures, icon fonts,
            multi-column layouts, and tables used for layout. This build reads
            the source you upload, extracts its text, and compares that text
            against the structured fields it recovered. It does not compile a
            PDF or run three ATS parsers.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
          {/* Human view */}
          <div className="border border-white/10 bg-paper text-ink">
            <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <span className="flex items-center gap-2 font-data text-[10px] uppercase tracking-[0.16em] text-muted">
                <span className="h-1.5 w-1.5 rounded-full bg-ok" />
                as a human reads it
              </span>
              <span className="font-data text-[10px] text-ok">clean</span>
            </div>
            <div className="p-4 sm:p-5">
              <pre className="overflow-x-auto whitespace-pre-wrap font-body text-[12.5px] leading-relaxed text-ink">
                {humanLines.join("\n")}
              </pre>
            </div>
            <div className="border-t border-line bg-redline-soft/30 px-4 py-3 sm:px-5">
              <p className="font-data text-[9px] uppercase tracking-[0.16em] text-redline">
                what disappears
              </p>
              <p className="mt-1 text-caption leading-relaxed text-ink">
                Spaced letters, ligature glyphs, and image-based sections.
              </p>
            </div>
            <div className="border-t border-line px-4 py-2.5 font-data text-[9px] uppercase tracking-[0.14em] text-muted">
              visual reading order · intact
            </div>
          </div>

          {/* Machine view */}
          <div className="relative overflow-hidden border border-white/10 bg-[#0B110C]">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
              <span className="flex items-center gap-2 font-data text-[10px] uppercase tracking-[0.16em] text-slate-400">
                <span className="h-1.5 w-1.5 rounded-full bg-redline" />
                text the engine extracted
              </span>
              <span className="font-data text-[10px] text-rose-300">
                sample · 3 issues
              </span>
            </div>

            <div className="overflow-x-auto p-4 sm:p-5">
              <pre className="font-data text-[11.5px] leading-relaxed">
                {machineLines.map((line, index) => (
                  <div key={`${line.text}-${index}`} className="flex">
                    <span className="w-7 shrink-0 select-none pr-3 text-right text-slate-700">
                      {index + 1}
                    </span>
                    <span
                      className={`min-w-0 whitespace-pre-wrap break-words ${
                        line.issue
                          ? "-ml-1 border-l-2 border-redline bg-redline/10 px-2 text-rose-300"
                          : "text-slate-300"
                      }`}
                    >
                      {line.text || " "}
                    </span>
                  </div>
                ))}
              </pre>

              <div className="mt-4 space-y-1.5 border-t border-white/10 pt-3">
                {machineLines
                  .filter((line) => line.issue)
                  .map((line) => (
                    <p
                      key={line.issue}
                      className="font-data text-[10px] leading-relaxed text-rose-300/80"
                    >
                      ↳ {line.issue}
                    </p>
                  ))}
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-white/10 px-4 py-2.5 font-data text-[9px] uppercase tracking-[0.14em] text-slate-500">
              <span>reading order · interrupted</span>
              <span>1,284 chars</span>
            </div>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 font-data text-[10px] text-slate-500">
          <span className="flex items-center gap-2">
            <span className="h-2 w-2 bg-ok" /> extractable
          </span>
          <span className="flex items-center gap-2">
            <span className="h-2 w-2 bg-redline" /> parse issue
          </span>
          <span className="text-slate-500/80">
            extract text → structure fields → compare → attach a source
            reference when available
          </span>
        </div>
      </div>
    </section>
  );
}

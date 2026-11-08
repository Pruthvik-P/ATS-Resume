import Link from "next/link";
import { Navbar } from "@/components/navbar";
import { HeroScan } from "@/components/hero-scan";
import { ScanTranscript } from "@/components/scan-transcript";
import { ScoreLedger } from "@/components/score-ledger";
import { AtsXRay } from "@/components/ats-xray";
import { Guardrails } from "@/components/guardrails";
import { Faq } from "@/components/faq";
import { Footer } from "@/components/footer";

const facts = [
  ["7", "weighted components"],
  ["1", "job at a time"],
  ["0", "invented facts"],
  ["1", "human in the loop"],
];

const formatGroups = [
  {
    label: "Input",
    items: ["PDF", "DOCX", "LaTeX (.tex / .zip)", "Plain text (.txt)"],
    note: "Text is extracted, then structured heuristically into a JSON Resume subset.",
  },
  {
    label: "Output",
    items: ["Score report", "Parse issues", "Change proposals"],
    note: "Review each proposal. PDF and DOCX export are not in this build.",
  },
  {
    label: "Engine",
    items: ["pypdf / PyMuPDF", "python-docx", "LaTeX static analysis"],
    note: "One extractor per format. OCR and multi-parser comparison are not enabled.",
  },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:bg-ink focus:px-4 focus:py-2 focus:text-caption focus:text-paper"
      >
        Skip to content
      </a>

      <Navbar />

      <main id="main" className="flex-1">
        {/* Hero — the scan sheet is the thesis */}
        <section className="relative overflow-hidden border-b border-line bg-paper">
          <div
            aria-hidden="true"
            className="grid-paper pointer-events-none absolute inset-0 opacity-70 fade-mask-b"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-32 -top-40 h-[34rem] w-[34rem] rounded-full bg-accent-soft/50 blur-3xl"
          />

          <div className="relative mx-auto grid max-w-[1240px] grid-cols-1 items-center gap-14 px-5 pb-14 pt-14 sm:px-8 sm:pb-16 sm:pt-20 lg:grid-cols-[1.04fr_0.96fr] lg:gap-16 lg:pb-20 lg:pt-24">
            <div>
              <div className="animate-rise flex items-center gap-2.5">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                <span className="eyebrow text-muted">
                  AI ATS optimiser · evidence-first
                </span>
              </div>

              <p
                className="animate-rise mt-8 font-data text-[11px] uppercase tracking-[0.2em] text-redline"
                style={{ animationDelay: "80ms" }}
              >
                More applications. Less signal.
              </p>

              <h1
                className="text-display animate-rise mt-3 text-ink"
                style={{ animationDelay: "140ms" }}
              >
                Stop guessing
                <br />
                what the machine sees.
              </h1>

              <p
                className="animate-rise mt-7 max-w-xl text-small leading-relaxed text-muted sm:text-body"
                style={{ animationDelay: "220ms" }}
              >
                ats.resume parses your resume source, extracts its text, scores
                seven weighted components, and proposes only the edits your own
                experience supports. You approve every line.
              </p>

              <div
                className="animate-rise mt-8 flex flex-col gap-3 sm:flex-row sm:items-center"
                style={{ animationDelay: "300ms" }}
              >
                <Link
                  href="/start"
                  className="group inline-flex h-12 items-center justify-center gap-3 bg-ink px-6 text-small font-semibold text-paper transition-colors hover:bg-ink-2"
                >
                  Run a scan
                  <span
                    aria-hidden="true"
                    className="font-data text-[12px] transition-transform group-hover:translate-x-0.5"
                  >
                    →
                  </span>
                </Link>
                <Link
                  href="#xray"
                  className="inline-flex h-12 items-center justify-center border border-ink/20 px-6 text-small font-medium text-ink transition-colors hover:bg-bg"
                >
                  See the X-Ray
                </Link>
              </div>

              <ul
                className="animate-rise mt-8 flex flex-wrap gap-x-5 gap-y-2 font-data text-[9px] uppercase tracking-[0.13em] text-muted"
                style={{ animationDelay: "380ms" }}
              >
                <li className="flex items-center gap-1.5">
                  <span className="text-ok">✓</span> no account required
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-ok">✓</span> every edit carries a source
                  reference
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-ok">✓</span> nothing auto-submits
                </li>
              </ul>
            </div>

            <div
              className="animate-rise min-w-0 lg:pl-2"
              style={{ animationDelay: "260ms" }}
            >
              <HeroScan />
            </div>
          </div>

          {/* Factual strip — not decoration */}
          <div className="relative border-t border-line">
            <div className="mx-auto grid max-w-[1240px] grid-cols-2 px-5 sm:grid-cols-4 sm:px-8">
              {facts.map(([number, label], index) => (
                <div
                  key={label}
                  className={`flex items-baseline gap-2.5 py-4 sm:py-5 ${
                    index % 2 === 1 ? "pl-5 sm:pl-6" : "sm:pl-6 sm:first:pl-0"
                  } ${
                    index < 2 ? "border-b border-line sm:border-b-0" : ""
                  } sm:border-l sm:border-line`}
                >
                  <span className="font-display text-2xl font-bold leading-none text-ink">
                    {number}
                  </span>
                  <span className="font-data text-[9px] uppercase leading-relaxed tracking-[0.14em] text-muted">
                    {label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* The premise */}
        <section className="border-b border-white/10 bg-ink text-paper">
          <div className="mx-auto max-w-[1240px] px-5 py-16 sm:px-8 sm:py-20">
            <div className="grid grid-cols-1 gap-8 lg:grid-cols-[0.16fr_1fr]">
              <span
                aria-hidden="true"
                className="font-display text-6xl leading-[0.7] text-accent-soft/30"
              >
                &ldquo;
              </span>
              <div>
                <p className="max-w-3xl font-display text-[clamp(1.7rem,3.3vw,2.9rem)] font-medium leading-[1.1] tracking-[-0.03em] text-paper">
                  Most resume tools optimise for a number. This one optimises
                  for a resume you can defend in the room.
                </p>
                <div className="mt-8 flex flex-col gap-3 border-t border-white/10 pt-4 sm:flex-row sm:items-center sm:justify-between">
                  <p className="font-data text-[9px] uppercase tracking-[0.16em] text-slate-500">
                    the premise behind ats.resume
                  </p>
                  <Link
                    href="#scoring"
                    className="group inline-flex items-center gap-2 font-data text-[10px] uppercase tracking-[0.14em] text-slate-300 transition-colors hover:text-paper"
                  >
                    read the scoring method
                    <span
                      aria-hidden="true"
                      className="transition-transform group-hover:translate-x-0.5"
                    >
                      →
                    </span>
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* What it is */}
        <section
          id="how-it-works"
          className="scroll-mt-20 border-b border-line bg-paper"
        >
          <div className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-28">
            <div className="grid grid-cols-1 gap-12 lg:grid-cols-[1.02fr_0.98fr] lg:gap-20">
              <div>
                <span className="eyebrow text-muted">what it is</span>
                <h2 className="text-h2 mt-4 text-ink">
                  A diagnostic,
                  <br />
                  not a score generator.
                </h2>
                <p className="mt-6 max-w-xl text-small leading-relaxed text-muted sm:text-body">
                  ats.resume is a diagnostic for one job at a time. It does not
                  hand you a number and a rewritten CV. It parses your source,
                  extracts the text the engine can recover, analyses the job
                  description, and scores seven components. Then it proposes
                  changes — with a source reference and rationale attached to
                  each one.
                </p>
                <p className="mt-4 max-w-xl text-small leading-relaxed text-muted">
                  One input, one job, one honest read. No queue of auto-applied
                  roles. No spray and pray.
                </p>

                <div className="mt-8 border-t border-line">
                  {[
                    ["How the X-Ray works", "#xray"],
                    ["Read the scoring rubric", "#scoring"],
                    ["See the guardrails", "#guardrails"],
                  ].map(([label, href]) => (
                    <Link
                      key={label}
                      href={href}
                      className="group flex items-center justify-between gap-4 border-b border-line py-3.5 text-small font-medium text-ink transition-colors hover:text-accent"
                    >
                      <span>{label}</span>
                      <span
                        aria-hidden="true"
                        className="font-data text-[11px] text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-accent"
                      >
                        →
                      </span>
                    </Link>
                  ))}
                </div>
              </div>

              <div className="self-start lg:pt-3">
                <ScanTranscript />
                <p className="mt-3 font-data text-[9px] leading-relaxed text-muted">
                  Illustrative output from a real engine run. Numbers vary by
                  document. LaTeX is parsed as source text; compilation and PDF
                  export are not in this build.
                </p>
              </div>
            </div>
          </div>
        </section>

        <ScoreLedger />
        <AtsXRay />
        <Guardrails />

        {/* Inputs and outputs */}
        <section id="formats" className="scroll-mt-20 border-b border-line bg-bg">
          <div className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-24">
            <div className="grid grid-cols-1 gap-10 lg:grid-cols-[0.86fr_1.14fr] lg:gap-16">
              <div>
                <span className="eyebrow text-muted">inputs &amp; outputs</span>
                <h2 className="text-h2 mt-4 text-ink">
                  Resume in.
                  <br />
                  Evidence out.
                </h2>
                <p className="mt-5 max-w-md text-small leading-relaxed text-muted">
                  PDF, DOCX, LaTeX and plain text are all first-class inputs. The
                  engine extracts text, analyses the LaTeX source for ATS risks,
                  scores what it can recover, and tells you what it lost.
                  Sandboxed compilation and PDF export are Phase 2, not this
                  build.
                </p>
              </div>

              <div className="grid gap-px border border-line bg-line sm:grid-cols-3">
                {formatGroups.map((group) => (
                  <div key={group.label} className="bg-paper p-5">
                    <p className="font-data text-[9px] uppercase tracking-[0.18em] text-muted">
                      {group.label}
                    </p>
                    <ul className="mt-3 flex flex-wrap gap-1.5">
                      {group.items.map((item) => (
                        <li
                          key={item}
                          className="border border-line bg-bg/60 px-2 py-1 font-data text-[10px] text-ink"
                        >
                          {item}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-4 text-caption leading-relaxed text-muted">
                      {group.note}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <Faq />

        {/* Final CTA */}
        <section className="bg-paper">
          <div className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-24">
            <div className="relative overflow-hidden border border-line bg-ink px-6 py-12 text-paper sm:px-10 sm:py-16 lg:px-14">
              <div
                aria-hidden="true"
                className="grid-dark pointer-events-none absolute inset-0 opacity-60"
              />
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-accent/20 blur-3xl"
              />

              <div className="relative">
                <span className="eyebrow text-slate-500">
                  ready when you are
                </span>
                <h2 className="text-h2 mt-4 max-w-2xl text-paper">
                  Bring a resume and one job description.
                </h2>
                <p className="mt-5 max-w-xl text-small leading-relaxed text-slate-400">
                  You get a score, the gaps behind it, and proposals you can
                  defend. Every edit waits for your accept or reject. Nothing is
                  submitted to an employer.
                </p>
                <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                  <Link
                    href="/start"
                    className="group inline-flex h-12 items-center justify-center gap-3 bg-paper px-6 text-small font-semibold text-ink transition-colors hover:bg-accent-soft"
                  >
                    Run a scan
                    <span
                      aria-hidden="true"
                      className="font-data text-[12px] transition-transform group-hover:translate-x-0.5"
                    >
                      →
                    </span>
                  </Link>
                  <Link
                    href="#scoring"
                    className="inline-flex h-12 items-center justify-center border border-white/20 px-6 text-small font-medium text-paper transition-colors hover:bg-white/5"
                  >
                    Read the method
                  </Link>
                </div>
                <p className="mt-5 font-data text-[9px] uppercase tracking-[0.14em] text-slate-500">
                  local engine · stored on the scan host · no auto-apply
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}

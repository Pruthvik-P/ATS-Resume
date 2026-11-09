import type { Metadata } from "next";
import Link from "next/link";
import { Navbar } from "@/components/navbar";
import { UploadForm } from "@/components/upload-form";
import { Footer } from "@/components/footer";

export const metadata: Metadata = {
  title: "Start a scan — ATS.Resume",
  description:
    "Upload a resume and one job description to get an explainable ATS score, the parse issues behind it, and a rewrite you can defend.",
};

const outcomes = [
  {
    label: "score",
    title: "A score you can audit",
    body: "Seven weighted components, published caps, and the evidence behind each number.",
  },
  {
    label: "parse",
    title: "The parse issues",
    body: "What the engine extracts from your source — including the parts it loses.",
  },
  {
    label: "rewrite",
    title: "Edits you approve",
    body: "Each proposal carries a source reference and rationale. Accept or reject each one.",
  },
];

export default function StartPage() {
  return (
    <div className="flex flex-1 flex-col">
      <Navbar />

      <main className="flex-1">
        <section className="relative overflow-hidden border-b border-line bg-paper">
          <div
            aria-hidden="true"
            className="grid-paper pointer-events-none absolute inset-0 opacity-60 fade-mask-b"
          />
          <div className="relative mx-auto max-w-[1240px] px-5 pb-10 pt-10 sm:px-8 sm:pb-12 sm:pt-14">
            <Link
              href="/"
              className="group inline-flex items-center gap-2 font-data text-[9px] uppercase tracking-[0.16em] text-muted transition-colors hover:text-ink"
            >
              <span
                aria-hidden="true"
                className="transition-transform group-hover:-translate-x-0.5"
              >
                ←
              </span>
              back to overview
            </Link>

            <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-[1fr_0.82fr] lg:items-start lg:gap-16">
              <div>
                <div className="flex items-center gap-2.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                  <span className="eyebrow text-muted">scan / new</span>
                </div>
                <h1 className="text-h2 mt-4 text-ink">
                  Start with one job.
                </h1>
                <p className="mt-4 max-w-xl text-small leading-relaxed text-muted">
                  Upload your resume and paste or link the description you are
                  actually applying to. One document, one role, one honest read —
                  no queue, no auto-apply.
                </p>
              </div>

              <div className="border border-line bg-bg/60">
                <p className="border-b border-line px-4 py-2.5 font-data text-[9px] uppercase tracking-[0.16em] text-muted">
                  what you get back
                </p>
                <div className="divide-y divide-line">
                  {outcomes.map((outcome) => (
                    <div
                      key={outcome.label}
                      className="flex gap-3 px-4 py-3"
                    >
                      <span className="pt-0.5 font-data text-[9px] uppercase tracking-[0.14em] text-accent">
                        {outcome.label}
                      </span>
                      <div>
                        <p className="text-caption font-semibold text-ink">
                          {outcome.title}
                        </p>
                        <p className="mt-0.5 text-caption leading-relaxed text-muted">
                          {outcome.body}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="bg-bg">
          <UploadForm />
        </section>
      </main>

      <Footer />
    </div>
  );
}

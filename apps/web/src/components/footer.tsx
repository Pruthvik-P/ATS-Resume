import Link from "next/link";

const columns = [
  {
    title: "Product",
    links: [
      { label: "Overview", href: "/" },
      { label: "How it works", href: "/#how-it-works" },
      { label: "The X-Ray", href: "/#xray" },
      { label: "Start a scan", href: "/start" },
    ],
  },
  {
    title: "Method",
    links: [
      { label: "Scoring", href: "/#scoring" },
      { label: "Guardrails", href: "/#guardrails" },
      { label: "Inputs & outputs", href: "/#formats" },
      { label: "FAQ", href: "/#faq" },
    ],
  },
  {
    title: "Limits",
    links: [
      { label: "Scores are a proxy", href: "/#scoring" },
      { label: "No auto-apply", href: "/#guardrails" },
      { label: "Preview build", href: "/start" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="bg-ink text-paper">
      <div className="mx-auto max-w-[1240px] px-5 py-14 sm:px-8 sm:py-16">
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[1.3fr_2fr]">
          <div>
            <Link
              href="/"
              className="font-display text-2xl font-bold tracking-[-0.04em]"
            >
              ats<span className="text-accent-soft">.</span>resume
            </Link>
            <p className="mt-4 max-w-xs text-small leading-relaxed text-slate-400">
              An evidence-first ATS optimiser. Built to show its work, cite its
              sources, and leave the final decision with you.
            </p>
            <p className="mt-6 inline-flex items-center gap-2 border border-white/10 px-2.5 py-1.5 font-data text-[9px] uppercase tracking-[0.14em] text-slate-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              preview build 0.4
            </p>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            {columns.map((column) => (
              <div key={column.title}>
                <p className="font-data text-[9px] uppercase tracking-[0.18em] text-slate-500">
                  {column.title}
                </p>
                <ul className="mt-4 space-y-2.5">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      <Link
                        href={link.href}
                        className="text-caption text-slate-300 transition-colors hover:text-paper"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-white/10 pt-6 font-data text-[9px] leading-relaxed text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 ats.resume · frontend preview</p>
          <p className="max-w-md sm:text-right">
            Not affiliated with any ATS vendor. No score is ground truth. No
            change is submitted without you.
          </p>
        </div>
      </div>
    </footer>
  );
}

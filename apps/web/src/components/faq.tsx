const faqs = [
  {
    question: "Is there a universal ATS score?",
    answer:
      "No. Workday, Greenhouse, Lever, iCIMS and Taleo mostly parse, store and rank; few auto-reject on a number. Our score is a calibrated proxy built from seven weighted components, with the rubric and caps published. Use it to find real gaps, not as ground truth.",
  },
  {
    question: "Does it apply to jobs for me?",
    answer:
      "No. ats.resume prepares the application up to the click: it scores the role, tailors the resume, and shows every change with its source. You review the edit and submit it yourself. Mass auto-apply damages your standing with recruiters — and it is not what this tool is for.",
  },
  {
    question: "Can it invent experience, titles or metrics?",
    answer:
      "No. The rewriter may only draw from your resume and your confirmed facts bank. Every changed bullet carries the source spans it draws from. If a claim cannot be traced, it fails closed. When a metric would help but is not provided, the tool inserts [ADD METRIC: …] and asks you for the real number.",
  },
  {
    question: "What resumes can I upload?",
    answer:
      "PDF, DOCX, and LaTeX (.tex or .zip). LaTeX is a first-class input: we parse the source into an AST so macros survive, compile it in a sandbox, and score the extracted PDF. That lets us fix parse problems at the source instead of flattening your layout.",
  },
  {
    question: "Why is LaTeX treated differently?",
    answer:
      "Because a LaTeX PDF can look perfect to a human and parse badly in an ATS. Ligatures, icon fonts, multi-column layouts and tables used for layout all corrupt extraction. We compile, extract with three ATS-like parsers, compare field by field, and cite the exact source line that breaks.",
  },
  {
    question: "Where does my resume data live?",
    answer:
      "The architecture keeps resumes encrypted at rest and in transit, supports retention limits and one-click deletion, and can redact PII before model calls. The AI provider you choose should offer zero-retention terms; self-hosting is an option for sensitive tenants. This page is a frontend preview — the engine and storage layer are being wired next.",
  },
];

export function Faq() {
  return (
    <section id="faq" className="scroll-mt-20 border-b border-line bg-bg">
      <div className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[0.84fr_1.16fr] lg:gap-20">
          <div>
            <span className="eyebrow text-muted">questions</span>
            <h2 className="text-h2 mt-4 text-ink">
              The things worth
              <br />
              being sceptical about.
            </h2>
            <p className="mt-5 max-w-sm text-small leading-relaxed text-muted">
              No black box, no miracle score. If something here sounds too
              confident, it probably is — these are the limits we build around.
            </p>
          </div>

          <div className="border-y border-line">
            {faqs.map((faq) => (
              <details
                key={faq.question}
                className="faq-item group border-b border-line py-5 last:border-0"
              >
                <summary className="flex cursor-pointer list-none items-start justify-between gap-6 text-left">
                  <span className="text-small font-semibold text-ink">
                    {faq.question}
                  </span>
                  <span
                    aria-hidden="true"
                    className="faq-plus mt-0.5 shrink-0 font-data text-lg leading-none text-muted transition-transform duration-200"
                  >
                    +
                  </span>
                </summary>
                <p className="mt-3 max-w-2xl text-small leading-relaxed text-muted">
                  {faq.answer}
                </p>
              </details>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

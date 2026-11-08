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
      "No. The deterministic optimiser only reorders existing skills, fixes parse issues, replaces weak phrases with past-tense verbs it can trace, or inserts a placeholder asking for a missing number. The verifier rejects new employers, products, proper nouns, and unsupported numbers. Missing must-haves become questions, not inserted claims. An LLM provider is pluggable, but the default build uses a deterministic stub.",
  },
  {
    question: "What resumes can I upload?",
    answer:
      "PDF, DOCX, LaTeX (.tex or .zip), and plain text. We extract the text, structure it into a JSON Resume subset, and score that. LaTeX is read as source text and checked statically for font-encoding, ligature, table, multi-column, and hostile-input risks. This build does not compile LaTeX or export a PDF.",
  },
  {
    question: "Why is LaTeX treated differently?",
    answer:
      "Because a LaTeX PDF can look perfect to a human and parse badly in an ATS. The engine analyses the source for missing ToUnicode maps, T1 font encoding, ligatures, icon fonts, tables, and multi-column layouts, then scores the text it can recover. It cites the source line when available. It does not claim three-parser agreement or a sandboxed compile.",
  },
  {
    question: "Where does my resume data live?",
    answer:
      "In this build, resumes and job descriptions are stored by the FastAPI engine: SQLite locally or PostgreSQL via Compose, with uploaded files on the API host. Authentication is a single shared API key when configured. Per-user auth, encryption at rest, and retention controls are not implemented yet. The API exposes DELETE /v1/resumes/{id}.",
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

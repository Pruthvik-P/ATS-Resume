const lines = [
  {
    kind: "command",
    text: "scan --describe",
  },
  {
    kind: "ok",
    label: "input",
    text: "jane_doe.tex · staff-engineer.txt",
  },
  {
    kind: "ok",
    label: "parse",
    text: "resume.tex → canonical · 1,284 tokens",
  },
  {
    kind: "ok",
    label: "compile",
    text: "Tectonic → PDF · 1.2s",
  },
  {
    kind: "warn",
    label: "extract",
    text: "3 parse issues → see the X-Ray",
  },
  {
    kind: "ok",
    label: "analyse",
    text: "JD → 14 must-have · 9 nice-to-have",
  },
  {
    kind: "ok",
    label: "score",
    text: "78 / 100 · calibrated proxy",
  },
  {
    kind: "ok",
    label: "optimise",
    text: "11 changes · 0 unsupported claims",
  },
] as const;

export function ScanTranscript() {
  return (
    <div className="border border-ink/15 bg-ink text-paper">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-2 font-data text-[10px] uppercase tracking-[0.16em] text-slate-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          scan transcript
          <span className="text-slate-600">/</span>
          <span className="text-slate-300">sample</span>
        </div>
        <span className="font-data text-[9px] uppercase tracking-[0.16em] text-slate-500">
          not a live run
        </span>
      </div>

      <div className="px-4 py-5 sm:px-5">
        <div className="space-y-2.5 font-data text-[11px] leading-relaxed">
          {lines.map((line) => {
            if (line.kind === "command") {
              return (
                <p key={line.text} className="flex gap-2 text-slate-300">
                  <span className="text-accent-soft">$</span>
                  <span>{line.text}</span>
                </p>
              );
            }

            return (
              <div key={line.label} className="flex gap-3">
                <span
                  className={`w-3 shrink-0 text-center ${
                    line.kind === "warn" ? "text-amber-300" : "text-emerald-400"
                  }`}
                >
                  {line.kind === "warn" ? "!" : "✓"}
                </span>
                <span className="w-[4.5rem] shrink-0 text-slate-500">
                  {line.label}
                </span>
                <span
                  className={
                    line.kind === "warn" ? "text-amber-200" : "text-slate-300"
                  }
                >
                  {line.text}
                </span>
              </div>
            );
          })}
        </div>

        <div className="mt-5 border-t border-white/10 pt-3">
          <p className="font-data text-[10px] text-slate-500">
            status:{" "}
            <span className="text-paper">waiting for your review</span>
            <span className="cursor-blink ml-0.5 inline-block h-[1em] w-[0.5em] translate-y-[0.12em] bg-accent-soft/80" />
          </p>
        </div>
      </div>
    </div>
  );
}

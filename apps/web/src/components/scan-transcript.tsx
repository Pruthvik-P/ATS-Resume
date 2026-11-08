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
    text: "resume.tex → source text · 1,284 chars",
  },
  {
    kind: "ok",
    label: "structure",
    text: "heuristic → 2 roles · 2 skill groups",
  },
  {
    kind: "warn",
    label: "extract",
    text: "1 parse warning → see the X-Ray",
  },
  {
    kind: "ok",
    label: "analyse",
    text: "JD → 6 must-have · 3 nice-to-have",
  },
  {
    kind: "ok",
    label: "score",
    text: "55.9 / 100 · capped at 70",
  },
  {
    kind: "ok",
    label: "optimise",
    text: "4 proposals · 2 need your input",
  },
] as const;

export function ScanTranscript() {
  return (
    <div className="border border-white/10 bg-night text-on-night">
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
                  <span className="text-on-night-accent">$</span>
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
            <span className="text-on-night">waiting for your review</span>
            <span className="cursor-blink ml-0.5 inline-block h-[1em] w-[0.5em] translate-y-[0.12em] bg-on-night-accent/80" />
          </p>
        </div>
      </div>
    </div>
  );
}

import { diffWords } from "@/lib/diff";

export function WordDiff({
  before,
  after,
}: {
  before: string;
  after: string;
}) {
  const tokens = diffWords(before, after);
  return (
    <div className="mt-2 border border-line bg-bg/40 p-2.5">
      <p className="mb-1.5 font-data text-[9px] uppercase tracking-[0.14em] text-muted">
        word diff
      </p>
      <p className="whitespace-pre-wrap text-caption leading-relaxed text-ink/80">
        {tokens.map((token, index) => (
          <span
            key={`${index}-${token.kind}`}
            className={
              token.kind === "delete"
                ? "bg-redline-soft text-redline line-through decoration-redline/60"
                : token.kind === "insert"
                  ? "bg-ok-soft text-ok"
                  : undefined
            }
          >
            {token.value}
          </span>
        ))}
      </p>
    </div>
  );
}

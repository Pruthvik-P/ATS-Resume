export type DiffKind = "equal" | "insert" | "delete";

export interface DiffToken {
  value: string;
  kind: DiffKind;
}

function tokenize(text: string): string[] {
  return text.match(/\s+|[^\s]+/g) ?? [];
}

export function diffWords(before: string, after: string): DiffToken[] {
  const left = tokenize(before);
  const right = tokenize(after);
  // Keep this bounded; the proposal panes are short bullets.
  if (left.length > 600 || right.length > 600) {
    return [
      { value: before, kind: "delete" },
      { value: after, kind: "insert" },
    ];
  }

  const rows = left.length + 1;
  const cols = right.length + 1;
  const table: number[][] = Array.from({ length: rows }, () =>
    Array<number>(cols).fill(0),
  );
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        left[i] === right[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const tokens: DiffToken[] = [];
  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    if (left[i] === right[j]) {
      tokens.push({ value: left[i], kind: "equal" });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      tokens.push({ value: left[i], kind: "delete" });
      i += 1;
    } else {
      tokens.push({ value: right[j], kind: "insert" });
      j += 1;
    }
  }
  while (i < left.length) {
    tokens.push({ value: left[i], kind: "delete" });
    i += 1;
  }
  while (j < right.length) {
    tokens.push({ value: right[j], kind: "insert" });
    j += 1;
  }
  return tokens;
}

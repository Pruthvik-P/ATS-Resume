import assert from "node:assert/strict";
import test from "node:test";

import { diffWords } from "../src/lib/diff.ts";

test("identical text produces only equal tokens", () => {
  const tokens = diffWords("Built FastAPI services.", "Built FastAPI services.");
  assert.ok(tokens.length > 0);
  assert.ok(tokens.every((token) => token.kind === "equal"));
});

test("changed words are marked insert/delete, not equal", () => {
  const tokens = diffWords("Responsible for building APIs.", "Built APIs.");
  assert.ok(tokens.some((token) => token.kind === "delete"));
  assert.ok(tokens.some((token) => token.kind === "insert"));
  assert.equal(
    tokens
      .filter((token) => token.kind !== "equal")
      .map((token) => token.value)
      .join("")
      .includes("Responsible"),
    true,
  );
});

test("empty side is represented as inserts or deletes", () => {
  const removed = diffWords("remove this bullet", "");
  assert.ok(removed.every((token) => token.kind === "delete"));
  const added = diffWords("", "add this bullet");
  assert.ok(added.every((token) => token.kind === "insert"));
});

test("long input falls back to two blocks", () => {
  const long = "word ".repeat(700);
  const tokens = diffWords(long, `${long}extra`);
  assert.deepEqual(
    tokens.map((token) => token.kind),
    ["delete", "insert"],
  );
});

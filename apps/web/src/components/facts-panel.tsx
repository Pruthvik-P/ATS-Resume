"use client";

import { useEffect, useState } from "react";
import { ApiError, createFact, deleteFact, listFacts } from "@/lib/api";
import type { Fact } from "@/lib/api-types";

export function FactsPanel() {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const body = await listFacts();
        if (!cancelled) setFacts(body.items);
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof ApiError
              ? loadError.message
              : "Could not load the Facts Bank.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const add = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    try {
      const fact = await createFact(value);
      setFacts((current) => [fact, ...current]);
      setText("");
    } catch (addError) {
      setError(
        addError instanceof ApiError
          ? addError.message
          : "The fact could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteFact(id);
      setFacts((current) => current.filter((fact) => fact.id !== id));
    } catch (removeError) {
      setError(
        removeError instanceof ApiError
          ? removeError.message
          : "The fact could not be deleted.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="border border-line bg-paper">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          <span className="eyebrow text-muted">facts bank</span>
        </div>
        <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
          {facts.length} confirmed fact{facts.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="p-4 sm:p-5">
        <p className="text-caption leading-relaxed text-muted">
          Add only things that are true and can be defended in an interview.
          Facts are available to future optimiser runs and missing-skill
          questions — they are never inserted automatically.
        </p>

        <form onSubmit={add} className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="e.g. Led migration of 14 services to Kubernetes in 2024"
            maxLength={2000}
            className="min-w-0 flex-1 border border-line bg-bg/40 px-3 py-2 text-caption text-ink outline-none transition-colors placeholder:text-muted/70 focus:border-accent focus:bg-paper"
          />
          <button
            type="submit"
            disabled={!text.trim() || busy}
            className="inline-flex h-9 items-center justify-center border border-accent/40 bg-accent-soft px-4 font-data text-[10px] uppercase tracking-[0.1em] text-accent-strong transition-colors hover:bg-accent hover:text-brand-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            Add fact
          </button>
        </form>

        {error && (
          <p className="mt-2 border border-redline/25 bg-redline-soft p-2 text-caption text-redline">
            {error}
          </p>
        )}

        <div className="mt-3 divide-y divide-line border border-line">
          {loading ? (
            <p className="px-3 py-3 text-caption text-muted">Loading facts…</p>
          ) : facts.length === 0 ? (
            <p className="px-3 py-3 text-caption text-muted">
              No facts yet. Missing-skill questions stay unanswered until you
              add evidence here.
            </p>
          ) : (
            facts.map((fact) => (
              <div
                key={fact.id}
                className="flex items-start justify-between gap-3 px-3 py-2.5"
              >
                <div>
                  <p className="text-caption leading-relaxed text-ink">
                    {fact.fact_text}
                  </p>
                  <p className="mt-0.5 font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                    {fact.source}
                    {fact.tags.length ? ` · ${fact.tags.join(" · ")}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void remove(fact.id)}
                  disabled={busy}
                  className="shrink-0 font-data text-[9px] uppercase tracking-[0.12em] text-muted underline underline-offset-4 transition-colors hover:text-redline disabled:opacity-40"
                >
                  delete
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}

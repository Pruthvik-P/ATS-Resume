"use client";

import { useState } from "react";
import { ApiError, deleteAccount, purgeAccount } from "@/lib/api";

export function PrivacyPanel() {
  const [days, setDays] = useState("30");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const removeAll = async () => {
    const confirmed = window.confirm(
      "Delete every resume, JD, score, job, fact, and stored file for this account? This cannot be undone.",
    );
    if (!confirmed || busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await deleteAccount();
      setMessage(
        `Deleted ${result.deleted.resumes_deleted} resume(s), ${result.deleted.jds_deleted} JD(s), and ${result.deleted.facts_deleted} fact(s). One audit tombstone was retained.`,
      );
    } catch (deleteError) {
      setError(
        deleteError instanceof ApiError
          ? deleteError.message
          : "The account data could not be deleted.",
      );
    } finally {
      setBusy(false);
    }
  };

  const purge = async () => {
    const parsed = Number.parseInt(days, 10);
    if (!Number.isFinite(parsed) || parsed < 1 || busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await purgeAccount(parsed);
      setMessage(
        `Purged ${result.resumes_deleted} resume(s), ${result.versions_deleted} version(s), and ${result.storage_objects_deleted} stored file(s) older than ${parsed} day(s).`,
      );
    } catch (purgeError) {
      setError(
        purgeError instanceof ApiError
          ? purgeError.message
          : "The retention purge failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="border border-line bg-paper">
      <summary className="cursor-pointer px-5 py-3 font-data text-[9px] uppercase tracking-[0.14em] text-muted">
        privacy / data controls
      </summary>
      <div className="border-t border-line p-4 sm:p-5">
        <p className="text-caption leading-relaxed text-muted">
          Deleting is explicit and removes derived versions, scores, jobs,
          facts, and stored files. A retention purge keeps newer rows and
          deletes anything older than the window.
        </p>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
            purge older than
            <input
              value={days}
              onChange={(event) => setDays(event.target.value)}
              inputMode="numeric"
              className="ml-2 w-16 border border-line bg-bg/40 px-2 py-1 text-caption text-ink outline-none focus:border-accent"
            />
            days
          </label>
          <button
            type="button"
            onClick={() => void purge()}
            disabled={busy}
            className="inline-flex h-8 items-center border border-line bg-paper px-3 font-data text-[9px] uppercase tracking-[0.1em] text-muted transition-colors hover:border-accent hover:text-accent disabled:opacity-40"
          >
            Purge old data
          </button>
          <button
            type="button"
            onClick={() => void removeAll()}
            disabled={busy}
            className="inline-flex h-8 items-center border border-redline/30 bg-redline-soft px-3 font-data text-[9px] uppercase tracking-[0.1em] text-redline transition-colors hover:bg-redline hover:text-paper disabled:opacity-40"
          >
            Delete all my data
          </button>
        </div>

        {message && (
          <p className="mt-3 border border-ok/25 bg-ok-soft p-2 text-caption text-ok">
            {message}
          </p>
        )}
        {error && (
          <p className="mt-3 border border-redline/25 bg-redline-soft p-2 text-caption text-redline">
            {error}
          </p>
        )}
      </div>
    </details>
  );
}

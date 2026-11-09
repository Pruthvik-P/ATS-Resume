"use client";

import { useEffect, useState } from "react";
import { ApiError, getVersionDiff, listVersions, versionExportUrl } from "@/lib/api";
import type {
  FieldDiff,
  ResumeVersionRead,
  VersionDiffResponse,
} from "@/lib/api-types";

function eventText(event: Record<string, unknown>, key: string): string {
  const value = event[key];
  return typeof value === "string" ? value : "";
}

export function VersionHistoryPanel({
  resumeId,
  refreshKey,
}: {
  resumeId: string;
  refreshKey: number;
}) {
  const [versions, setVersions] = useState<ResumeVersionRead[]>([]);
  const [diff, setDiff] = useState<VersionDiffResponse | null>(null);
  const [preview, setPreview] = useState<ResumeVersionRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [diffLoading, setDiffLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const body = await listVersions(resumeId);
        if (!cancelled) setVersions(body);
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof ApiError
              ? loadError.message
              : "Could not load version history.",
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
  }, [resumeId, refreshKey]);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setVersions(await listVersions(resumeId));
    } catch (loadError) {
      setError(
        loadError instanceof ApiError
          ? loadError.message
          : "Could not load version history.",
      );
    } finally {
      setLoading(false);
    }
  };

  const showDiff = async (version: ResumeVersionRead, against?: string) => {
    setDiffLoading(true);
    setError(null);
    try {
      setDiff(await getVersionDiff(version.id, against));
    } catch (diffError) {
      setError(
        diffError instanceof ApiError
          ? diffError.message
          : "Could not compare versions.",
      );
    } finally {
      setDiffLoading(false);
    }
  };

  return (
    <section className="border border-line bg-paper">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          <span className="eyebrow text-muted">versions / export</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
            {versions.length} version{versions.length === 1 ? "" : "s"}
          </span>
          <button
            type="button"
            onClick={() => void refresh()}
            className="font-data text-[9px] uppercase tracking-[0.12em] text-muted underline underline-offset-4 hover:text-ink"
          >
            refresh
          </button>
        </div>
      </div>

      <div className="p-4 sm:p-5">
        {error && (
          <p className="mb-3 border border-redline/25 bg-redline-soft p-2 text-caption text-redline">
            {error}
          </p>
        )}
        {loading ? (
          <p className="text-caption text-muted">Loading versions…</p>
        ) : versions.length === 0 ? (
          <p className="text-caption text-muted">
            No versions yet. Accept or reject a proposal to create an immutable
            snapshot.
          </p>
        ) : (
          <div className="space-y-3">
            {versions.map((version, index) => {
              const previous = versions[index + 1];
              const decisions = version.change_log.filter(
                (event) => event.type === "change_decision",
              );
              return (
                <article key={version.id} className="border border-line">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-bg/40 px-3 py-2">
                    <div>
                      <p className="font-data text-[10px] uppercase tracking-[0.12em] text-ink">
                        version {version.version}
                        {index === 0 ? " · latest" : ""}
                      </p>
                      <p className="mt-0.5 font-data text-[9px] text-muted">
                        {new Date(version.created_at).toLocaleString()} ·{" "}
                        {decisions.length} decision
                        {decisions.length === 1 ? "" : "s"}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 font-data text-[9px] uppercase tracking-[0.1em]">
                      {(["tex", "docx", "pdf", "json"] as const).map((format) => (
                        <a
                          key={format}
                          href={versionExportUrl(version.id, format)}
                          className="border border-line bg-paper px-2 py-1 text-muted transition-colors hover:border-accent hover:text-accent"
                          download
                        >
                          {format}
                        </a>
                      ))}
                      <a
                        href={versionExportUrl(version.id, "tex", "source")}
                        className="border border-line bg-paper px-2 py-1 text-muted transition-colors hover:border-accent hover:text-accent"
                        download
                      >
                        patched tex
                      </a>
                      <button
                        type="button"
                        onClick={() => setPreview(version)}
                        className="border border-line bg-paper px-2 py-1 text-muted transition-colors hover:border-accent hover:text-accent"
                      >
                        preview
                      </button>
                      {previous && (
                        <button
                          type="button"
                          onClick={() => void showDiff(version, previous.id)}
                          disabled={diffLoading}
                          className="border border-line bg-paper px-2 py-1 text-muted transition-colors hover:border-accent hover:text-accent disabled:opacity-40"
                        >
                          diff
                        </button>
                      )}
                    </div>
                  </div>

                  {decisions.length > 0 && (
                    <div className="divide-y divide-line">
                      {decisions.slice(-3).map((event, eventIndex) => (
                        <div
                          key={`${version.id}-${eventIndex}`}
                          className="px-3 py-2"
                        >
                          <p className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                            {eventText(event, "kind")} ·{" "}
                            {eventText(event, "status")}
                            {event.reverted ? " · reverted" : ""}
                          </p>
                          <p className="mt-1 line-clamp-2 text-caption text-ink/70">
                            <span className="text-redline">
                              {eventText(event, "before_text") ||
                                eventText(event, "original")}
                            </span>
                            <span className="mx-1 text-muted">→</span>
                            <span className="text-ok">
                              {eventText(event, "after_text") ||
                                eventText(event, "proposed")}
                            </span>
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}

        {preview && (
          <div className="mt-4 border border-line">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-bg/40 px-3 py-2">
              <p className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                pdf preview · version {preview.version}
              </p>
              <button
                type="button"
                onClick={() => setPreview(null)}
                className="font-data text-[9px] uppercase tracking-[0.12em] text-muted underline underline-offset-4 hover:text-ink"
              >
                close
              </button>
            </div>
            <iframe
              src={versionExportUrl(preview.id, "pdf")}
              title={`PDF preview for version ${preview.version}`}
              className="h-[560px] w-full bg-bg"
            />
            <p className="border-t border-line px-3 py-2 text-[10px] text-muted">
              PDF preview needs the sandboxed LaTeX compiler. If it is disabled,
              use the TEX or DOCX export instead.
            </p>
          </div>
        )}

        {diff && (
          <div className="mt-4 border border-line">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-bg/40 px-3 py-2">
              <p className="font-data text-[9px] uppercase tracking-[0.12em] text-muted">
                canonical diff · {diff.changed_fields} field
                {diff.changed_fields === 1 ? "" : "s"}
              </p>
              <button
                type="button"
                onClick={() => setDiff(null)}
                className="font-data text-[9px] uppercase tracking-[0.12em] text-muted underline underline-offset-4 hover:text-ink"
              >
                close
              </button>
            </div>
            <p className="border-b border-line px-3 py-2 text-[10px] text-muted">
              {diff.note}
            </p>
            {diff.fields.length === 0 ? (
              <p className="px-3 py-3 text-caption text-muted">
                No canonical field changes.
              </p>
            ) : (
              <div className="divide-y divide-line">
                {diff.fields.map((field: FieldDiff) => (
                  <div key={field.path} className="px-3 py-2">
                    <p className="font-data text-[9px] uppercase tracking-[0.1em] text-muted">
                      {field.path} · {field.change}
                    </p>
                    <p className="mt-1 text-caption leading-relaxed">
                      {field.before && (
                        <span className="text-redline line-through decoration-redline/40">
                          {field.before}
                        </span>
                      )}
                      {field.before && field.after && (
                        <span className="mx-1 text-muted">→</span>
                      )}
                      {field.after && <span className="text-ok">{field.after}</span>}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

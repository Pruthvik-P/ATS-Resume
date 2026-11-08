"use client";

import { useLayoutEffect } from "react";

const STORAGE_KEY = "ats-theme";

export function ThemeToggle() {
  // React Strict Mode resets <html> on the dev remount, which clears the
  // class the inline bootstrap script set. Re-apply it before paint.
  useLayoutEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      const dark =
        stored === "dark" || stored === "light"
          ? stored === "dark"
          : window.matchMedia("(prefers-color-scheme: dark)").matches;
      document.documentElement.classList.toggle("dark", dark);
      document.documentElement.style.colorScheme = dark ? "dark" : "light";
    } catch {
      // localStorage can be unavailable in restricted contexts.
    }
  }, []);

  function toggleTheme() {
    const root = document.documentElement;
    const next = root.classList.contains("dark") ? "light" : "dark";
    root.classList.toggle("dark", next === "dark");
    root.style.colorScheme = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The toggle still works for this page view.
    }
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title="Toggle colour theme"
      aria-label="Toggle colour theme"
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center border border-line text-muted transition-colors hover:border-ink/30 hover:text-ink"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-4 w-4 dark:hidden"
      >
        <path d="M17 12.2A6.8 6.8 0 0 1 7.8 3a7 7 0 1 0 9.2 9.2Z" />
      </svg>
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        className="hidden h-4 w-4 dark:block"
      >
        <circle cx="10" cy="10" r="3.1" />
        <path d="M10 1.6v2.1M10 16.3v2.1M1.6 10h2.1M16.3 10h2.1M4 4l1.5 1.5M14.5 14.5 16 16M16 4l-1.5 1.5M5.5 14.5 4 16" />
      </svg>
    </button>
  );
}

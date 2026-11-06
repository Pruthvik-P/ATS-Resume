"use client";

import Link from "next/link";
import { useState } from "react";

const links = [
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#xray", label: "The X-Ray" },
  { href: "/#scoring", label: "Scoring" },
  { href: "/#faq", label: "FAQ" },
];

function ScanMark() {
  return (
    <span
      aria-hidden="true"
      className="relative inline-flex h-5 w-5 items-center justify-center"
    >
      <svg
        viewBox="0 0 20 20"
        fill="none"
        className="h-5 w-5"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        <path d="M3 7V3h4M13 3h4v4M17 13v4h-4M7 17H3v-4" />
        <path d="M6 10h8" />
      </svg>
    </span>
  );
}

export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-paper/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1240px] items-center justify-between px-5 sm:px-8">
        <Link
          href="/"
          className="group flex items-center gap-2.5 text-ink"
          onClick={() => setOpen(false)}
        >
          <ScanMark />
          <span className="font-display text-[1.02rem] font-bold tracking-[-0.03em]">
            ats<span className="text-accent">.</span>resume
          </span>
        </Link>

        <nav
          aria-label="Primary"
          className="hidden items-center gap-1 md:flex"
        >
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="px-3 py-2 text-caption font-medium text-muted transition-colors hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2.5">
          <span className="hidden items-center gap-2 font-data text-[10px] uppercase tracking-[0.14em] text-muted lg:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" />
            preview build
          </span>
          <Link
            href="/start"
            className="group inline-flex h-9 items-center gap-2 border border-ink bg-ink px-4 text-caption font-semibold text-paper transition-colors hover:bg-ink-2"
          >
            Run a scan
            <span
              aria-hidden="true"
              className="font-data text-[11px] transition-transform group-hover:translate-x-0.5"
            >
              →
            </span>
          </Link>
          <button
            type="button"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((value) => !value)}
            className="inline-flex h-9 w-9 items-center justify-center border border-line text-ink md:hidden"
          >
            <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
            <svg
              aria-hidden="true"
              viewBox="0 0 20 20"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
            >
              {open ? (
                <path d="M4 4l12 12M16 4L4 16" />
              ) : (
                <path d="M3 6h14M3 10h14M3 14h14" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {open && (
        <div id="mobile-nav" className="border-t border-line bg-paper md:hidden">
          <nav aria-label="Mobile" className="px-5 py-3">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="block border-b border-line/70 py-3 text-small font-medium text-ink last:border-0"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}

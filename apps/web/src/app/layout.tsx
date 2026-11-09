import type { Metadata } from "next";
import {
  Instrument_Serif,
  Inter,
  JetBrains_Mono,
} from "next/font/google";
import "./globals.css";

const instrument = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-instrument-serif",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ats.resume — Stop guessing what the machine sees.",
  description:
    "An evidence-first ATS resume optimiser that shows its work. Parse, analyse the job description, score seven weighted components, and propose only edits your own experience supports.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${instrument.variable} ${inter.variable} ${jetbrains.variable} antialiased`}
    >
      <head>
        {/* Runs while the HTML is parsed, before the first paint. The class
            set here is the same one the toggle writes, so there is no flash. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=localStorage.getItem("ats-theme");var d=s?s==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;var r=document.documentElement;r.classList.toggle("dark",d);r.style.colorScheme=d?"dark":"light";}catch(e){}})()`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Providers } from "@/components/Providers";

import "@fontsource-variable/archivo/wdth.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Homeworking – Was möchtest du bauen?",
  description:
    "Beschreibe dein Bauvorhaben und erhalte Varianten, Zeichnungen, Materialliste, Kosten und Bauanleitung.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eceeea" },
    { media: "(prefers-color-scheme: dark)", color: "#121614" },
  ],
};

/** A folding-rule segment with a house: measuring is the product. */
function Logo() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className="h-7 w-7">
      <rect width="32" height="32" rx="5" className="fill-accent" />
      <path
        d="M9 15 16 9l7 6v8H9v-8Z"
        fill="none"
        className="stroke-on-accent"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M4 32v-4M8 32v-2M12 32v-4M16 32v-2M20 32v-4M24 32v-2M28 32v-4"
        className="stroke-on-accent"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de">
      <body className="min-h-screen font-sans antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
        >
          Zum Inhalt springen
        </a>
        <header className="sticky top-0 z-40 h-14 border-b border-border bg-bg/80 backdrop-blur-md">
          <nav
            aria-label="Hauptnavigation"
            className="flex h-full items-center justify-between gap-4 px-4 sm:px-6"
          >
            <Link
              href="/"
              className="flex items-center gap-2 text-xl font-extrabold [font-stretch:78%]"
            >
              <Logo />
              Homeworking
            </Link>
            <div className="flex items-center gap-1 sm:gap-2">
              <Link
                href="/projects"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-muted transition hover:bg-surface-muted hover:text-text"
              >
                Meine Projekte
              </Link>
              {/* A full page load on purpose: it resets the in-memory chat for a fresh start. */}
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
              <a
                href="/"
                className="inline-flex items-center gap-1.5 rounded-md bg-text px-3 py-1.5 text-sm font-semibold text-bg transition hover:opacity-90"
              >
                <svg
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeLinecap="round"
                >
                  <path d="M12 5v14M5 12h14" />
                </svg>
                <span className="hidden sm:inline">Neues Projekt</span>
                <span className="sr-only sm:hidden">Neues Projekt</span>
              </a>
            </div>
          </nav>
        </header>
        <Providers>
          <main id="main">{children}</main>
        </Providers>
        <footer className="border-t border-border">
          <div className="flex flex-wrap gap-x-6 gap-y-2 px-4 py-4 pb-20 text-sm text-muted sm:px-6 lg:pb-4">
            <span>Planungshilfe – kein Standsicherheitsnachweis.</span>
            <Link href="/impressum" className="underline underline-offset-2 hover:text-text">
              Impressum
            </Link>
            <Link href="/datenschutz" className="underline underline-offset-2 hover:text-text">
              Datenschutz
            </Link>
          </div>
        </footer>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Providers } from "@/components/Providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Homeworking – Was möchtest du bauen?",
  description:
    "Beschreibe dein Bauvorhaben und erhalte Varianten, Zeichnungen, Materialliste, Kosten und Bauanleitung.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de">
      <body className="min-h-screen font-sans antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
        >
          Zum Inhalt springen
        </a>
        <header className="border-b border-border bg-surface">
          <nav
            aria-label="Hauptnavigation"
            className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3"
          >
            <Link href="/" className="text-lg font-bold tracking-tight">
              Homeworking
            </Link>
            <Link href="/projects" className="text-sm font-medium text-muted hover:text-text">
              Meine Projekte
            </Link>
          </nav>
        </header>
        <Providers>
          <main id="main" className="mx-auto max-w-7xl px-4 py-6">
            {children}
          </main>
        </Providers>
        <footer className="border-t border-border">
          <div className="mx-auto flex max-w-7xl flex-wrap gap-x-6 gap-y-2 px-4 py-4 text-sm text-muted">
            <span>Planungshilfe – kein Standsicherheitsnachweis.</span>
            <Link href="/impressum" className="underline">
              Impressum
            </Link>
            <Link href="/datenschutz" className="underline">
              Datenschutz
            </Link>
          </div>
        </footer>
      </body>
    </html>
  );
}

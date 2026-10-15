import { Workspace } from "@/components/Workspace";
import { useDocumentTitle } from "@/lib/title";

export function HomePage() {
  useDocumentTitle();
  // Keyed so that switching between "/" and a project page always starts a fresh workspace,
  // like a Next.js page segment did.
  return <Workspace key="new" />;
}

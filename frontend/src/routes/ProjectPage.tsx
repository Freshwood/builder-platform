import { useParams } from "react-router";

import { Workspace } from "@/components/Workspace";
import { useDocumentTitle } from "@/lib/title";

export function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  useDocumentTitle();
  // Remount per project: the workspace keeps the chat and the project id in local state.
  return <Workspace key={id} initialProjectId={id ?? null} />;
}

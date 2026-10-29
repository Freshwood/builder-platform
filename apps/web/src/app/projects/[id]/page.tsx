import { Workspace } from "@/components/Workspace";

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // The key remounts the workspace (chat, brief, project state) when the route switches to
  // another project in-app; it takes the project id only as its initial state.
  return <Workspace key={id} initialProjectId={id} />;
}

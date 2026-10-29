import {
  client,
  executeCommand,
  getProject,
  getVersion,
  listProjects,
  restoreVersion,
  undo,
  versions,
  type CommandRequest,
  type CommandResponse,
  type ProjectListEntry,
  type ProjectView,
  type VersionEntry,
} from "@/api";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { sessionReady } from "@/lib/session";

// The Next.js server proxies /api to the backend, so requests stay same-origin.
client.setConfig({ baseUrl: "", credentials: "include" });
client.interceptors.request.use(async (request) => {
  await sessionReady();
  return request;
});

// Query keys. The version list and the read-only versions live below projectKey, so
// invalidating a project refreshes its version data as well.
export const projectsKey = ["projects"] as const;
export const projectKey = (id: string) => ["project", id] as const;
export const versionsKey = (id: string) => [...projectKey(id), "versions"] as const;
export const versionKey = (id: string, seq: number | null) =>
  [...projectKey(id), "version", seq] as const;

/** Refetch a project (and everything below it) and the project list after the server changed it. */
export function invalidateProject(queryClient: QueryClient, id: string) {
  void queryClient.invalidateQueries({ queryKey: projectKey(id) });
  void queryClient.invalidateQueries({ queryKey: projectsKey });
}

/**
 * Show the project a command, undo or restore returned right away and refresh what depends on
 * it: the version list and the project list (title, summary, timestamp).
 */
function applyProjectResponse(queryClient: QueryClient, id: string, response: CommandResponse) {
  const view: ProjectView = {
    project: response.project,
    can_undo: response.can_undo,
    seq: response.seq,
  };
  queryClient.setQueryData(projectKey(id), view);
  void queryClient.invalidateQueries({ queryKey: versionsKey(id) });
  void queryClient.invalidateQueries({ queryKey: projectsKey });
}

export function useProject(id: string | null) {
  return useQuery({
    queryKey: projectKey(id ?? "none"),
    enabled: Boolean(id),
    queryFn: async (): Promise<ProjectView> => {
      const { data } = await getProject({ path: { project_id: id! }, throwOnError: true });
      return data;
    },
  });
}

export function useVersions(id: string) {
  return useQuery({
    queryKey: versionsKey(id),
    queryFn: async (): Promise<VersionEntry[]> =>
      (await versions({ path: { project_id: id }, throwOnError: true })).data,
  });
}

/** Read-only state of a project after version ``seq``; old versions never change. */
export function useProjectVersion(id: string, seq: number | null) {
  return useQuery({
    queryKey: versionKey(id, seq),
    enabled: seq !== null,
    staleTime: Infinity,
    queryFn: async (): Promise<ProjectView> =>
      (await getVersion({ path: { project_id: id, seq: seq! }, throwOnError: true })).data,
  });
}

const byRecentChange = (projects: ProjectListEntry[]): ProjectListEntry[] =>
  [...projects].sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));

/** The user's projects, most recently changed first. */
export function useProjects() {
  return useQuery({
    queryKey: projectsKey,
    queryFn: async () => (await listProjects({ throwOnError: true })).data,
    // A module-level function: TanStack memoises the selection per data and function identity.
    select: byRecentChange,
  });
}

function errorMessage(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    return Array.isArray(detail) ? detail.map(String).join("; ") : String(detail);
  }
  return "Die Änderung konnte nicht gespeichert werden.";
}

type Outcome = { data?: CommandResponse; error?: unknown };

/** A mutation that changes the project on the server and answers with the new state. */
function useProjectMutation<Variables>(
  id: string,
  run: (variables: Variables) => Promise<Outcome>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (variables: Variables): Promise<CommandResponse> => {
      const { data, error } = await run(variables);
      if (error || !data) throw new Error(errorMessage(error));
      return data;
    },
    onSuccess: (response) => applyProjectResponse(queryClient, id, response),
  });
}

export function useProjectCommand(id: string) {
  return useProjectMutation(id, (command: CommandRequest["command"]) =>
    executeCommand({ path: { project_id: id }, body: { command } }),
  );
}

export function useUndo(id: string) {
  return useProjectMutation<void>(id, () => undo({ path: { project_id: id } }));
}

export function useRestoreVersion(id: string) {
  return useProjectMutation(id, (seq: number) => restoreVersion({ path: { project_id: id, seq } }));
}

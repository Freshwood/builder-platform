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
  type ProjectView,
  type VersionEntry,
} from "@homeworking/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sessionReady } from "@/lib/session";

// The Next.js server proxies /api to the backend, so requests stay same-origin.
client.setConfig({ baseUrl: "", credentials: "include" });
client.interceptors.request.use(async (request) => {
  await sessionReady();
  return request;
});

export const projectKey = (id: string) => ["project", id] as const;
// Below projectKey, so invalidating a project also refreshes its version list.
const versionsKey = (id: string) => ["project", id, "versions"] as const;

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

export function useVersions(id: string, enabled = true) {
  return useQuery({
    queryKey: versionsKey(id),
    enabled,
    queryFn: async (): Promise<VersionEntry[]> =>
      (await versions({ path: { project_id: id }, throwOnError: true })).data,
  });
}

/** Read-only state of a project after version ``seq``; old versions never change. */
export function useProjectVersion(id: string, seq: number | null) {
  return useQuery({
    queryKey: ["project", id, "version", seq],
    enabled: seq !== null,
    staleTime: Infinity,
    queryFn: async (): Promise<ProjectView> =>
      (await getVersion({ path: { project_id: id, seq: seq! }, throwOnError: true })).data,
  });
}

export function useRestoreVersion(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (seq: number): Promise<CommandResponse> => {
      const { data, error } = await restoreVersion({ path: { project_id: id, seq } });
      if (error || !data) throw new Error(errorMessage(error));
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(projectKey(id), { project: data.project, can_undo: data.can_undo });
      void queryClient.invalidateQueries({ queryKey: versionsKey(id) });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: async () => (await listProjects({ throwOnError: true })).data,
  });
}

function errorMessage(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    return Array.isArray(detail) ? detail.map(String).join("; ") : String(detail);
  }
  return "Die Änderung konnte nicht gespeichert werden.";
}

export function useProjectCommand(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (command: CommandRequest["command"]): Promise<CommandResponse> => {
      const { data, error } = await executeCommand({
        path: { project_id: id },
        body: { command },
      });
      if (error || !data) throw new Error(errorMessage(error));
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(projectKey(id), { project: data.project, can_undo: data.can_undo });
      void queryClient.invalidateQueries({ queryKey: versionsKey(id) });
    },
  });
}

export function useUndo(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<CommandResponse> => {
      const { data, error } = await undo({ path: { project_id: id } });
      if (error || !data) throw new Error(errorMessage(error));
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(projectKey(id), { project: data.project, can_undo: data.can_undo });
      void queryClient.invalidateQueries({ queryKey: versionsKey(id) });
    },
  });
}

export function formatEur(value: string | number): string {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

import {
  client,
  executeCommand,
  getProject,
  listProjects,
  undo,
  type CommandRequest,
  type CommandResponse,
  type ProjectView,
} from "@homeworking/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

// The Next.js server proxies /api to the backend, so requests stay same-origin.
client.setConfig({ baseUrl: "", credentials: "include" });

export const projectKey = (id: string) => ["project", id] as const;

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

import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type APIRequestContext, type APIResponse } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));

/** One event of the AI SDK UI message stream (server-sent events). */
export type StreamEvent = { type: string; [key: string]: unknown };

/** Plain copy of an HTTP response, so steps can inspect it after the request context changes. */
export type Reply = {
  status: number;
  headers: Record<string, string>;
  body: Buffer;
  json: any;
};

/** State of one backend scenario: the guest session, the current project and the last reply. */
export class ApiWorld {
  chatId = randomUUID();
  projectId: string | undefined;
  rememberedProjectId: string | undefined;
  rememberedCost: string | undefined;
  reply: Reply | undefined;
  events: StreamEvent[] = [];
  view: any;

  constructor(readonly request: APIRequestContext) {}

  /** Replace `{projekt}` in a path with the current project id. */
  path(template: string): string {
    return template.replaceAll("{projekt}", this.projectId ?? "kein-projekt");
  }

  async call(method: "GET" | "POST" | "DELETE", path: string, data?: unknown): Promise<Reply> {
    const response = await this.request.fetch(this.path(path), { method, data });
    this.reply = await toReply(response);
    return this.reply;
  }

  async get(path: string): Promise<Reply> {
    return this.call("GET", path);
  }

  async post(path: string, data?: unknown): Promise<Reply> {
    return this.call("POST", path, data);
  }

  /** Send one chat message and collect the streamed answer. */
  async chat(text: string): Promise<StreamEvent[]> {
    const body = {
      trigger: "submit-message",
      id: this.chatId,
      projectId: this.projectId,
      messages: [{ id: randomUUID(), role: "user", parts: [{ type: "text", text }] }],
    };
    const reply = await this.post("/api/chat", body);
    expect(reply.status, reply.body.toString()).toBe(200);
    this.events = parseStream(reply.body.toString("utf-8"));
    for (const event of this.events) {
      const output = event.output as { project?: { project_id?: string } } | undefined;
      if (event.type === "tool-output-available" && output?.project?.project_id) {
        this.projectId = output.project.project_id;
      }
    }
    if (this.projectId) await this.refresh();
    return this.events;
  }

  /** Reload the current project into `view`. */
  async refresh(): Promise<any> {
    const reply = await this.get("/api/projects/{projekt}");
    expect(reply.status, reply.body.toString()).toBe(200);
    this.view = reply.json;
    return this.view;
  }

  /** Apply a project command and keep the new state. */
  async command(command: Record<string, unknown>): Promise<Reply> {
    const reply = await this.post("/api/projects/{projekt}/commands", { command });
    if (reply.status === 200) this.view = reply.json;
    return reply;
  }

  get project(): any {
    expect(this.view, "Es ist kein Projekt geladen").toBeTruthy();
    return this.view.project;
  }

  /** Text the assistant streamed in this turn. */
  get answerText(): string {
    return this.events
      .filter((e) => e.type === "text-delta")
      .map((e) => String(e.delta ?? ""))
      .join("");
  }

  get toolCalls(): string[] {
    return this.events
      .filter((e) => e.type === "tool-input-available" || e.type === "tool-input-start")
      .map((e) => String(e.toolName));
  }
}

export async function toReply(response: APIResponse): Promise<Reply> {
  const body = await response.body();
  let json: any;
  try {
    json = JSON.parse(body.toString("utf-8"));
  } catch {
    json = undefined;
  }
  return { status: response.status(), headers: response.headers(), body, json };
}

export function parseStream(raw: string): StreamEvent[] {
  return raw
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .filter((data) => data && data !== "[DONE]")
    .map((data) => JSON.parse(data) as StreamEvent);
}

/** Load a design from `fixtures/designs/<name>.json`. */
export function loadDesign(name: string): any {
  return JSON.parse(readFileSync(join(HERE, "..", "fixtures", "designs", `${name}.json`), "utf-8"));
}

/** Parse a table cell as JSON, or keep it as text when it is not valid JSON. */
export function cellValue(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

/**
 * Set a value at a simple path such as `parts[0].material`, `params[2].max` or `category`.
 * `parts[+]` appends to a list.
 */
export function setPath(target: any, path: string, value: unknown): void {
  const tokens = path.replace(/\[(\d+|\+)\]/g, ".$1").split(".");
  let node = target;
  for (const [index, token] of tokens.entries()) {
    const last = index === tokens.length - 1;
    if (token === "+") {
      if (!last) throw new Error(`[+] darf nur am Ende stehen: ${path}`);
      node.push(value);
      return;
    }
    const key = /^\d+$/.test(token) ? Number(token) : token;
    if (last) {
      node[key] = value;
      return;
    }
    node = node[key];
    if (node == null) throw new Error(`Pfad ${path} existiert nicht (bei ${token})`);
  }
}

/** Read a value at a dotted path, e.g. `project.result.summary`. */
export function getPath(source: any, path: string): unknown {
  return (path.match(/[^.[\]]+/g) ?? []).reduce(
    (node, key) => (node == null ? undefined : node[/^\d+$/.test(key) ? Number(key) : key]),
    source,
  );
}

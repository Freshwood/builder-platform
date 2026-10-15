import { expect } from "@playwright/test";
import type { DataTable } from "playwright-bdd";

import { Given, Then, When } from "../support/fixtures";
import { cellValue, getPath, loadDesign, setPath, toReply } from "../support/world";

// ---------------------------------------------------------------------------------------------
// Session and plain HTTP
// ---------------------------------------------------------------------------------------------

Given("ich bin ein neuer Gast", async ({ api }) => {
  const reply = await api.get("/api/me");
  expect(reply.status).toBe(200);
  expect(reply.json.is_guest).toBe(true);
});

When("ich {string} abrufe", async ({ api }, path: string) => {
  await api.get(path);
});

When("ich {string} ohne Inhalt sende", async ({ api }, path: string) => {
  await api.post(path);
});

When("ich {string} lösche", async ({ api }, path: string) => {
  await api.call("DELETE", path);
});

Then("ist der Statuscode {int}", async ({ api }, status: number) => {
  expect(api.reply?.status, api.reply?.body.toString().slice(0, 500)).toBe(status);
});

Then("hat das Feld {string} den Wert {string}", async ({ api }, path: string, value: string) => {
  expect(String(getPath(api.reply?.json, path))).toBe(value);
});

Then("enthält das Feld {string} den Text {string}", async ({ api }, path: string, text: string) => {
  expect(String(getPath(api.reply?.json, path))).toContain(text);
});

Then("ist der Inhaltstyp {string}", async ({ api }, type: string) => {
  expect(api.reply?.headers["content-type"] ?? "").toContain(type);
});

Then("beginnt die Antwort mit {string}", async ({ api }, prefix: string) => {
  expect(api.reply?.body.subarray(0, prefix.length).toString("utf-8")).toBe(prefix);
});

Then("ist die Antwort größer als {int} Bytes", async ({ api }, size: number) => {
  expect(api.reply?.body.length ?? 0).toBeGreaterThan(size);
});

Then("enthält die Antwort {string}", async ({ api }, text: string) => {
  expect(api.reply?.body.toString("utf-8")).toContain(text);
});

Then(
  "enthält der Header {string} den Text {string}",
  async ({ api }, header: string, text: string) => {
    expect(api.reply?.headers[header.toLowerCase()] ?? "").toContain(text);
  },
);

Then("bekomme ich bei erneutem Abruf von {string} dieselbe Gast-ID", async ({ api }, path) => {
  const first = await api.get(path);
  const second = await api.get(path);
  expect(second.json.id).toBe(first.json.id);
});

When("ein anderer Gast {string} abruft", async ({ api, playwright, baseURL }, path: string) => {
  const other = await playwright.request.newContext({ baseURL });
  try {
    api.reply = await toReply(await other.get(api.path(path)));
  } finally {
    await other.dispose();
  }
});

// ---------------------------------------------------------------------------------------------
// Chat with the assistant (offline model in tests)
// ---------------------------------------------------------------------------------------------

When("ich im Chat schreibe {string}", async ({ api }, text: string) => {
  await api.chat(text);
});

Given("ich habe im Chat {string} geplant", async ({ api }, text: string) => {
  await api.chat(text);
  expect(api.projectId, "Der Assistent hat kein Projekt angelegt").toBeTruthy();
});

Then("ruft der Assistent das Werkzeug {string} auf", async ({ api }, tool: string) => {
  expect(api.toolCalls).toContain(tool);
});

Then("ruft der Assistent kein Werkzeug auf", async ({ api }) => {
  expect(api.toolCalls).toEqual([]);
});

Then("antwortet der Assistent mit {string}", async ({ api }, text: string) => {
  expect(api.answerText).toContain(text);
});

Then("ist der Antwort-Stream vollständig", async ({ api }) => {
  const types = api.events.map((e) => e.type);
  expect(types[0]).toBe("start");
  expect(types.at(-1)).toBe("finish");
});

Then("wurde kein Projekt angelegt", async ({ api }) => {
  expect(api.projectId).toBeUndefined();
  const list = await api.get("/api/projects");
  expect(list.json).toEqual([]);
});

// ---------------------------------------------------------------------------------------------
// Project state
// ---------------------------------------------------------------------------------------------

Then("lautet die Projektzusammenfassung {string}", async ({ api }, summary: string) => {
  expect(api.project.result.summary).toBe(summary);
});

Then("hat das Projekt den Titel {string}", async ({ api }, title: string) => {
  expect(api.project.inputs.title).toBe(title);
});

Then("hat der Parameter {string} den Wert {string}", async ({ api }, name: string, value) => {
  expect(String(api.project.result.effective_params[name])).toBe(value);
});

Then("trägt das Projekt den Hinweis {string}", async ({ api }, code: string) => {
  expect(api.project.result.notices.map((n: { code: string }) => n.code)).toContain(code);
});

Then("trägt das Projekt nicht den Hinweis {string}", async ({ api }, code: string) => {
  expect(api.project.result.notices.map((n: { code: string }) => n.code)).not.toContain(code);
});

Then("enthält die Stückliste {string}", async ({ api }, name: string) => {
  const names = api.project.result.bom.map((line: { name: string }) => line.name);
  expect(names.join(" | ")).toContain(name);
});

Then("enthält die Zuschnittliste das Teil {string}", async ({ api }, part: string) => {
  expect(api.project.result.cut_list.map((c: { part: string }) => c.part)).toContain(part);
});

Then("enthält die Anleitung den Schritt {string}", async ({ api }, title: string) => {
  expect(api.project.result.instructions.map((s: { title: string }) => s.title)).toContain(title);
});

Then("hat das Projekt die Zeichnungen {string}", async ({ api }, views: string) => {
  const expected = views.split(",").map((v) => v.trim());
  const actual = api.project.result.drawings.map((d: { view: string }) => d.view);
  expect(actual).toEqual(expect.arrayContaining(expected));
});

Then("hat das Projekt ein 3D-Modell", async ({ api }) => {
  expect(api.project.result.solids.length).toBeGreaterThan(0);
});

Then("liegen die Materialkosten über {int} Euro", async ({ api }, euro: number) => {
  expect(Number(api.project.result.costs.material.min)).toBeGreaterThan(euro);
  expect(Number(api.project.result.costs.material.max)).toBeGreaterThanOrEqual(
    Number(api.project.result.costs.material.min),
  );
});

Given("ich merke mir die Materialkosten", async ({ api }) => {
  api.rememberedCost = JSON.stringify(api.project.result.costs.material);
});

Then("haben sich die Materialkosten geändert", async ({ api }) => {
  expect(JSON.stringify(api.project.result.costs.material)).not.toBe(api.rememberedCost);
});

Then("sind die Materialkosten wieder wie gemerkt", async ({ api }) => {
  expect(JSON.stringify(api.project.result.costs.material)).toBe(api.rememberedCost);
});

Given("ich merke mir das Projekt", async ({ api }) => {
  api.rememberedProjectId = api.projectId;
});

Then("ist es dasselbe Projekt wie gemerkt", async ({ api }) => {
  expect(api.projectId).toBe(api.rememberedProjectId);
});

Then("enthält meine Projektliste {string}", async ({ api }, text: string) => {
  const list = await api.get("/api/projects");
  const entries = list.json.map((p: { title: string; summary: string }) => `${p.title} ${p.summary}`);
  expect(entries.join(" | ")).toContain(text);
});

Then("kann ich rückgängig machen", async ({ api }) => {
  expect(api.view.can_undo).toBe(true);
});

Then("kann ich nichts mehr rückgängig machen", async ({ api }) => {
  expect(api.view.can_undo).toBe(false);
});

// ---------------------------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------------------------

When("ich den Parameter {string} auf {string} setze", async ({ api }, name: string, raw: string) => {
  await api.command({ type: "set_parameters", values: { [name]: cellValue(raw) } });
});

When("ich den Parameter {string} um {int} ändere", async ({ api }, name: string, delta: number) => {
  await api.command({ type: "change_parameter_by", name, delta });
});

When("ich die Variante {string} wähle", async ({ api }, key: string) => {
  await api.command({ type: "select_variant", variant_key: key });
});

When("ich das Projekt in {string} umbenenne", async ({ api }, title: string) => {
  await api.command({ type: "rename", title });
});

When("ich für {string} den Preis {string} eintrage", async ({ api }, item: string, price) => {
  await api.command({ type: "set_price", item_id: item, unit_price: price });
});

When("ich die Notiz {string} hinzufüge", async ({ api }, text: string) => {
  await api.command({ type: "add_note", text });
});

Then("ist die Änderung erfolgreich", async ({ api }) => {
  expect(api.reply?.status, api.reply?.body.toString()).toBe(200);
});

Then("wird die Änderung abgelehnt mit {string}", async ({ api }, text: string) => {
  expect([409, 422]).toContain(api.reply?.status);
  expect(JSON.stringify(api.reply?.json)).toContain(text);
});

Then("hat die Stückliste für {string} einen eigenen Preis", async ({ api }, item: string) => {
  const line = api.project.result.bom.find((l: { item_id: string }) => l.item_id === item);
  expect(line, `Keine Stücklistenzeile für ${item}`).toBeTruthy();
  expect(line.price_source).toBe("user");
});

When("ich die letzte Änderung rückgängig mache", async ({ api }) => {
  const reply = await api.post("/api/projects/{projekt}/undo");
  expect(reply.status, reply.body.toString()).toBe(200);
  api.view = reply.json;
});

// ---------------------------------------------------------------------------------------------
// Versions
// ---------------------------------------------------------------------------------------------

Then("zeigt der Verlauf neueste zuerst:", async ({ api }, table: DataTable) => {
  const reply = await api.get("/api/projects/{projekt}/versions");
  const labels = reply.json.map((v: { label: string }) => v.label);
  expect(labels).toEqual(table.raw().map((row) => row[0]));
});

Then("enthält der Verlauf {string}", async ({ api }, label: string) => {
  const reply = await api.get("/api/projects/{projekt}/versions");
  expect(reply.json.map((v: { label: string }) => v.label)).toContain(label);
});

Then("ist im Verlauf {string} die aktuelle Version", async ({ api }, label: string) => {
  const reply = await api.get("/api/projects/{projekt}/versions");
  const current = reply.json.filter((v: { current: boolean }) => v.current);
  expect(current.map((v: { label: string }) => v.label)).toEqual([label]);
});

When("ich Version {int} ansehe", async ({ api }, seq: number) => {
  const reply = await api.get(`/api/projects/{projekt}/versions/${seq}`);
  if (reply.status === 200) api.view = reply.json;
});

When("ich Version {int} wiederherstelle", async ({ api }, seq: number) => {
  const reply = await api.post(`/api/projects/{projekt}/versions/${seq}/restore`);
  expect(reply.status, reply.body.toString()).toBe(200);
  api.view = reply.json;
});

When("ich den aktuellen Stand neu lade", async ({ api }) => {
  await api.refresh();
});

// ---------------------------------------------------------------------------------------------
// Designs created directly (as the AI would save them)
// ---------------------------------------------------------------------------------------------

async function createFromDesign(
  api: import("../support/world").ApiWorld,
  name: string,
  changes: string[][] = [],
  params: Record<string, unknown> = {},
) {
  const design = loadDesign(name);
  for (const [path, value] of changes) setPath(design, path, cellValue(value));
  const reply = await api.post("/api/projects", { title: name, design, params });
  if (reply.status === 201) {
    api.view = reply.json;
    api.projectId = reply.json.project.id;
  }
}

When("ich ein Projekt aus dem Entwurf {string} anlege", async ({ api }, name: string) => {
  await createFromDesign(api, name);
});

When(
  "ich ein Projekt aus dem Entwurf {string} mit den Parametern {string} anlege",
  async ({ api }, name: string, params: string) => {
    await createFromDesign(api, name, [], JSON.parse(params));
  },
);

When(
  "ich ein Projekt aus dem Entwurf {string} mit diesen Änderungen anlege:",
  async ({ api }, name: string, table: DataTable) => {
    await createFromDesign(api, name, table.rows());
  },
);

Then("wird das Projekt angelegt", async ({ api }) => {
  expect(api.reply?.status, api.reply?.body.toString().slice(0, 800)).toBe(201);
});

Then("wird der Entwurf abgelehnt mit {string}", async ({ api }, text: string) => {
  expect(api.reply?.status, api.reply?.body.toString().slice(0, 800)).toBe(422);
  expect(JSON.stringify(api.reply?.json.detail)).toContain(text);
});

// ---------------------------------------------------------------------------------------------
// Chat history stored with the project
// ---------------------------------------------------------------------------------------------

Then("enthält der Chat-Verlauf des Projekts {string}", async ({ api }, text: string) => {
  const reply = await api.get("/api/projects/{projekt}/chat");
  expect(reply.status).toBe(200);
  expect(JSON.stringify(reply.json)).toContain(text);
});

Then("hat der Chat-Verlauf des Projekts {int} Nachrichten", async ({ api }, count: number) => {
  const reply = await api.get("/api/projects/{projekt}/chat");
  expect(reply.json).toHaveLength(count);
});

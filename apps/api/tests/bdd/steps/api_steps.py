"""Step definitions of the backend scenarios (German phrases, as in the feature files)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest_bdd import parsers, step

from ..world import ApiWorld, cell_value, get_path, js_str, load_design, set_path

# Steps use the generic ``step`` decorator: like cucumber, the keyword does not matter.

# --- Session and plain HTTP ---------------------------------------------------------------------


@step("ich bin ein neuer Gast")
def _new_guest(api: ApiWorld) -> None:
    reply = api.get("/api/me")
    assert reply.status == 200
    assert reply.json["is_guest"] is True


@step(parsers.parse('ich den Steckbrief "{text}" prüfe'))
def _check_brief(api: ApiWorld, text: str) -> None:
    api.post("/api/pipeline/intake", {"spec": {"description": text}})


@step(parsers.parse("ist die Planungszeit höchstens {seconds:d} Sekunden"))
def _planning_time(api: ApiWorld, seconds: int) -> None:
    assert api.chat_seconds <= seconds, f"{api.chat_seconds:.1f} s statt höchstens {seconds} s"


@step(parsers.parse('ich "{path}" abrufe'))
def _fetch(api: ApiWorld, path: str) -> None:
    api.get(path)


@step(parsers.parse('ich "{path}" ohne Inhalt sende'))
def _post_empty(api: ApiWorld, path: str) -> None:
    api.post(path)


@step(parsers.parse('ich "{path}" lösche'))
def _delete(api: ApiWorld, path: str) -> None:
    api.call("DELETE", path)


@step(parsers.parse("ist der Statuscode {status:d}"))
def _status(api: ApiWorld, status: int) -> None:
    assert api.reply is not None
    assert api.reply.status == status, api.reply.text[:500]


@step(parsers.parse('hat das Feld "{path}" den Wert "{value}"'))
def _field_value(api: ApiWorld, path: str, value: str) -> None:
    assert api.reply is not None
    assert js_str(get_path(api.reply.json, path)) == value


@step(parsers.parse('enthält das Feld "{path}" den Text "{text}"'))
def _field_contains(api: ApiWorld, path: str, text: str) -> None:
    assert api.reply is not None
    assert text in js_str(get_path(api.reply.json, path))


@step(parsers.parse('ist der Inhaltstyp "{kind}"'))
def _content_type(api: ApiWorld, kind: str) -> None:
    assert api.reply is not None
    assert kind in api.reply.headers.get("content-type", "")


@step(parsers.parse('beginnt die Antwort mit "{prefix}"'))
def _starts_with(api: ApiWorld, prefix: str) -> None:
    assert api.reply is not None
    assert api.reply.text.startswith(prefix)


@step(parsers.parse("ist die Antwort größer als {size:d} Bytes"))
def _bigger_than(api: ApiWorld, size: int) -> None:
    assert api.reply is not None
    assert len(api.reply.body) > size


@step(parsers.parse('enthält die Antwort "{text}"'))
def _body_contains(api: ApiWorld, text: str) -> None:
    assert api.reply is not None
    assert text in api.reply.text


@step(parsers.parse('enthält der Header "{header}" den Text "{text}"'))
def _header_contains(api: ApiWorld, header: str, text: str) -> None:
    assert api.reply is not None
    assert text in api.reply.headers.get(header.lower(), "")


@step(parsers.parse('bekomme ich bei erneutem Abruf von "{path}" dieselbe Gast-ID'))
def _same_guest(api: ApiWorld, path: str) -> None:
    first = api.get(path)
    second = api.get(path)
    assert second.json["id"] == first.json["id"]


@step(parsers.parse('ein anderer Gast "{path}" abruft'))
def _other_guest(api: ApiWorld, app: FastAPI, path: str) -> None:
    # A second client has its own cookie jar and therefore is another guest.
    with TestClient(app) as other:
        api.reply = ApiWorld.to_reply(other.get(api.path(path)))


# --- Chat with the assistant (offline model in tests) -------------------------------------------


@step(parsers.parse('ich im Chat schreibe "{text}"'))
def _chat(api: ApiWorld, text: str) -> None:
    api.chat(text)


@step(parsers.parse('ich habe im Chat "{text}" geplant'))
def _planned(api: ApiWorld, text: str) -> None:
    api.chat(text)
    assert api.project_id, "Der Assistent hat kein Projekt angelegt"


@step(parsers.parse('ruft der Assistent das Werkzeug "{tool}" auf'))
def _tool_called(api: ApiWorld, tool: str) -> None:
    assert tool in api.tool_calls


@step("ruft der Assistent kein Werkzeug auf")
def _no_tool(api: ApiWorld) -> None:
    assert api.tool_calls == []


@step(parsers.parse('antwortet der Assistent mit "{text}"'))
def _answers(api: ApiWorld, text: str) -> None:
    assert text in api.answer_text


@step("ist der Antwort-Stream vollständig")
def _stream_complete(api: ApiWorld) -> None:
    types = [e["type"] for e in api.events]
    assert types[0] == "start"
    assert types[-1] == "finish"


@step("wurde kein Projekt angelegt")
def _no_project(api: ApiWorld) -> None:
    assert api.project_id is None
    assert api.get("/api/projects").json == []


# --- Project state ------------------------------------------------------------------------------


@step(parsers.parse('lautet die Projektzusammenfassung "{summary}"'))
def _summary(api: ApiWorld, summary: str) -> None:
    assert api.project["result"]["summary"] == summary


@step(parsers.parse('hat das Projekt den Titel "{title}"'))
def _title(api: ApiWorld, title: str) -> None:
    assert api.project["inputs"]["title"] == title


@step(parsers.parse('hat der Parameter "{name}" den Wert "{value}"'))
def _param_value(api: ApiWorld, name: str, value: str) -> None:
    assert js_str(api.project["result"]["effective_params"].get(name)) == value


def _notice_codes(api: ApiWorld) -> list[str]:
    return [n["code"] for n in api.project["result"]["notices"]]


@step(parsers.parse('trägt das Projekt den Hinweis "{code}"'))
def _has_notice(api: ApiWorld, code: str) -> None:
    assert code in _notice_codes(api)


@step(parsers.parse('trägt das Projekt nicht den Hinweis "{code}"'))
def _has_no_notice(api: ApiWorld, code: str) -> None:
    assert code not in _notice_codes(api)


@step(parsers.parse('enthält die Stückliste "{name}"'))
def _bom_contains(api: ApiWorld, name: str) -> None:
    assert name in " | ".join(line["name"] for line in api.project["result"]["bom"])


@step(parsers.parse('enthält die Zuschnittliste das Teil "{part}"'))
def _cut_list_contains(api: ApiWorld, part: str) -> None:
    assert part in [c["part"] for c in api.project["result"]["cut_list"]]


@step(parsers.parse('enthält die Anleitung den Schritt "{title}"'))
def _instruction_step(api: ApiWorld, title: str) -> None:
    assert title in [s["title"] for s in api.project["result"]["instructions"]]


@step(parsers.parse('hat das Projekt die Zeichnungen "{views}"'))
def _drawings(api: ApiWorld, views: str) -> None:
    expected = [v.strip() for v in views.split(",")]
    actual = [d["view"] for d in api.project["result"]["drawings"]]
    assert all(view in actual for view in expected)


@step("hat das Projekt ein 3D-Modell")
def _has_solids(api: ApiWorld) -> None:
    assert len(api.project["result"]["solids"]) > 0


@step(parsers.parse("liegen die Materialkosten über {euro:d} Euro"))
def _material_cost_over(api: ApiWorld, euro: int) -> None:
    material = api.project["result"]["costs"]["material"]
    assert float(material["min"]) > euro
    assert float(material["max"]) >= float(material["min"])


def _material_cost(api: ApiWorld) -> str:
    return json.dumps(api.project["result"]["costs"]["material"], sort_keys=True)


@step("ich merke mir die Materialkosten")
def _remember_cost(api: ApiWorld) -> None:
    api.remembered_cost = _material_cost(api)


@step("haben sich die Materialkosten geändert")
def _cost_changed(api: ApiWorld) -> None:
    assert _material_cost(api) != api.remembered_cost


@step("sind die Materialkosten wieder wie gemerkt")
def _cost_restored(api: ApiWorld) -> None:
    assert _material_cost(api) == api.remembered_cost


@step("ich merke mir das Projekt")
def _remember_project(api: ApiWorld) -> None:
    api.remembered_project_id = api.project_id


@step("ist es dasselbe Projekt wie gemerkt")
def _same_project(api: ApiWorld) -> None:
    assert api.project_id == api.remembered_project_id


@step(parsers.parse('enthält meine Projektliste "{text}"'))
def _project_list_contains(api: ApiWorld, text: str) -> None:
    entries = [f"{p['title']} {p['summary']}" for p in api.get("/api/projects").json]
    assert text in " | ".join(entries)


@step("kann ich rückgängig machen")
def _can_undo(api: ApiWorld) -> None:
    assert api.view["can_undo"] is True


@step("kann ich nichts mehr rückgängig machen")
def _cannot_undo(api: ApiWorld) -> None:
    assert api.view["can_undo"] is False


# --- Commands -----------------------------------------------------------------------------------


@step(parsers.parse('ich den Parameter "{name}" auf "{raw}" setze'))
def _set_param(api: ApiWorld, name: str, raw: str) -> None:
    api.command({"type": "set_parameters", "values": {name: cell_value(raw)}})


@step(parsers.parse('ich den Parameter "{name}" um {delta:d} ändere'))
def _change_param(api: ApiWorld, name: str, delta: int) -> None:
    api.command({"type": "change_parameter_by", "name": name, "delta": delta})


@step(parsers.parse('ich die Variante "{key}" wähle'))
def _select_variant(api: ApiWorld, key: str) -> None:
    api.command({"type": "select_variant", "variant_key": key})


@step(parsers.parse('ich das Projekt in "{title}" umbenenne'))
def _rename(api: ApiWorld, title: str) -> None:
    api.command({"type": "rename", "title": title})


@step(parsers.parse('ich für "{item}" den Preis "{price}" eintrage'))
def _set_price(api: ApiWorld, item: str, price: str) -> None:
    api.command({"type": "set_price", "item_id": item, "unit_price": price})


@step(parsers.parse('ich die Notiz "{text}" hinzufüge'))
def _add_note(api: ApiWorld, text: str) -> None:
    api.command({"type": "add_note", "text": text})


@step("ist die Änderung erfolgreich")
def _change_ok(api: ApiWorld) -> None:
    assert api.reply is not None
    assert api.reply.status == 200, api.reply.text


@step(parsers.parse('wird die Änderung abgelehnt mit "{text}"'))
def _change_rejected(api: ApiWorld, text: str) -> None:
    assert api.reply is not None
    assert api.reply.status in (409, 422), api.reply.text[:500]
    assert text in json.dumps(api.reply.json, ensure_ascii=False)


@step(parsers.parse('hat die Stückliste für "{item}" einen eigenen Preis'))
def _bom_user_price(api: ApiWorld, item: str) -> None:
    line = next((x for x in api.project["result"]["bom"] if x["item_id"] == item), None)
    assert line, f"Keine Stücklistenzeile für {item}"
    assert line["price_source"] == "user"


@step("ich die letzte Änderung rückgängig mache")
def _undo(api: ApiWorld) -> None:
    reply = api.post("/api/projects/{projekt}/undo")
    assert reply.status == 200, reply.text
    api.view = reply.json


# --- Versions -----------------------------------------------------------------------------------


def _labels(api: ApiWorld) -> list[str]:
    return [v["label"] for v in api.get("/api/projects/{projekt}/versions").json]


@step("zeigt der Verlauf neueste zuerst:")
def _history_order(api: ApiWorld, datatable: list[list[str]]) -> None:
    assert _labels(api) == [row[0] for row in datatable]


@step(parsers.parse('enthält der Verlauf "{label}"'))
def _history_contains(api: ApiWorld, label: str) -> None:
    assert label in _labels(api)


@step(parsers.parse('ist im Verlauf "{label}" die aktuelle Version'))
def _history_current(api: ApiWorld, label: str) -> None:
    versions = api.get("/api/projects/{projekt}/versions").json
    assert [v["label"] for v in versions if v["current"]] == [label]


@step(parsers.parse("ich Version {seq:d} ansehe"))
def _view_version(api: ApiWorld, seq: int) -> None:
    reply = api.get(f"/api/projects/{{projekt}}/versions/{seq}")
    if reply.status == 200:
        api.view = reply.json


@step(parsers.parse("ich Version {seq:d} wiederherstelle"))
def _restore_version(api: ApiWorld, seq: int) -> None:
    reply = api.post(f"/api/projects/{{projekt}}/versions/{seq}/restore")
    assert reply.status == 200, reply.text
    api.view = reply.json


@step("ich den aktuellen Stand neu lade")
def _reload(api: ApiWorld) -> None:
    api.refresh()


# --- Designs created directly (as the AI would save them) ---------------------------------------


def _create_from_design(
    api: ApiWorld,
    name: str,
    changes: list[list[str]] | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    design = load_design(name)
    for path, value in changes or []:
        set_path(design, path, cell_value(value))
    reply = api.post("/api/projects", {"title": name, "design": design, "params": params or {}})
    if reply.status == 201:
        api.view = reply.json
        api.project_id = reply.json["project"]["id"]


@step(parsers.parse('ich ein Projekt aus dem Entwurf "{name}" anlege'))
def _create(api: ApiWorld, name: str) -> None:
    _create_from_design(api, name)


@step(
    parsers.parse('ich ein Projekt aus dem Entwurf "{name}" mit den Parametern "{params}" anlege')
)
def _create_with_params(api: ApiWorld, name: str, params: str) -> None:
    _create_from_design(
        api, name, params=json.loads(params.replace('\\"', '"'))
    )  # cucumber-style \" escape


@step(parsers.parse('ich ein Projekt aus dem Entwurf "{name}" mit diesen Änderungen anlege:'))
def _create_with_changes(api: ApiWorld, name: str, datatable: list[list[str]]) -> None:
    _create_from_design(api, name, datatable[1:])  # the first row is the header


@step("wird das Projekt angelegt")
def _created(api: ApiWorld) -> None:
    assert api.reply is not None
    assert api.reply.status == 201, api.reply.text[:800]


@step(parsers.parse('wird der Entwurf abgelehnt mit "{text}"'))
def _design_rejected(api: ApiWorld, text: str) -> None:
    assert api.reply is not None
    assert api.reply.status == 422, api.reply.text[:800]
    assert text in json.dumps(api.reply.json["detail"], ensure_ascii=False)


# --- Chat history stored with the project -------------------------------------------------------


@step(parsers.parse('enthält der Chat-Verlauf des Projekts "{text}"'))
def _chat_history_contains(api: ApiWorld, text: str) -> None:
    reply = api.get("/api/projects/{projekt}/chat")
    assert reply.status == 200
    assert text in json.dumps(reply.json, ensure_ascii=False)


@step(parsers.parse("hat der Chat-Verlauf des Projekts {count:d} Nachrichten"))
def _chat_history_count(api: ApiWorld, count: int) -> None:
    assert len(api.get("/api/projects/{projekt}/chat").json) == count

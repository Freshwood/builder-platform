"""World state and helpers for the backend BDD scenarios (port of the former TypeScript world)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

DESIGNS = Path(__file__).resolve().parent / "designs"


def parse_stream(raw: str) -> list[dict[str, Any]]:
    """Parse the AI SDK UI message stream (server-sent events) into events."""
    events: list[dict[str, Any]] = []
    for line in re.split(r"\r?\n", raw):
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data and data != "[DONE]":
            events.append(json.loads(data))
    return events


def load_design(name: str) -> Any:
    return json.loads((DESIGNS / f"{name}.json").read_text(encoding="utf-8"))


def cell_value(raw: str) -> Any:
    """Parse a table cell as JSON, or keep it as text when it is not valid JSON."""
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def set_path(target: Any, path: str, value: Any) -> None:
    """Set a value at a simple path such as ``parts[0].material``; ``parts[+]`` appends."""
    tokens = re.sub(r"\[(\d+|\+)\]", r".\1", path).split(".")
    node = target
    for index, token in enumerate(tokens):
        last = index == len(tokens) - 1
        if token == "+":
            if not last:
                raise ValueError(f"[+] darf nur am Ende stehen: {path}")
            node.append(value)
            return
        key: Any = int(token) if token.isdigit() else token
        if last:
            node[key] = value
            return
        node = node[key]
        if node is None:
            raise ValueError(f"Pfad {path} existiert nicht (bei {token})")


def get_path(source: Any, path: str) -> Any:
    """Read a value at a dotted path, e.g. ``project.result.summary``."""
    node = source
    for key in re.findall(r"[^.\[\]]+", path):
        if node is None:
            return None
        try:
            node = node[int(key) if key.isdigit() else key]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def js_str(value: Any) -> str:
    """Stringify like JavaScript's ``String()`` for the values the scenarios compare."""
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes
    json: Any

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class ApiWorld:
    """State of one backend scenario: the guest session, the current project and the last reply."""

    client: httpx.Client
    chat_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str | None = None
    remembered_project_id: str | None = None
    remembered_cost: str | None = None
    reply: Reply | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    view: Any = None

    def path(self, template: str) -> str:
        return template.replace("{projekt}", self.project_id or "kein-projekt")

    @staticmethod
    def to_reply(response: httpx.Response) -> Reply:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return Reply(
            response.status_code,
            {k.lower(): v for k, v in response.headers.items()},
            response.content,
            payload,
        )

    def call(self, method: str, path: str, data: Any = None) -> Reply:
        response = self.client.request(method, self.path(path), json=data)
        self.reply = self.to_reply(response)
        return self.reply

    def get(self, path: str) -> Reply:
        return self.call("GET", path)

    def post(self, path: str, data: Any = None) -> Reply:
        return self.call("POST", path, data)

    def chat(self, text: str) -> list[dict[str, Any]]:
        body = {
            "trigger": "submit-message",
            "id": self.chat_id,
            "projectId": self.project_id,
            "messages": [
                {"id": str(uuid.uuid4()), "role": "user", "parts": [{"type": "text", "text": text}]}
            ],
        }
        reply = self.post("/api/chat", body)
        assert reply.status == 200, reply.text
        self.events = parse_stream(reply.text)
        for event in self.events:
            output = event.get("output")
            if event.get("type") == "tool-output-available" and isinstance(output, dict):
                project = output.get("project")
                if isinstance(project, dict) and project.get("project_id"):
                    self.project_id = project["project_id"]
        if self.project_id:
            self.refresh()
        return self.events

    def refresh(self) -> Any:
        reply = self.get("/api/projects/{projekt}")
        assert reply.status == 200, reply.text
        self.view = reply.json
        return self.view

    def command(self, command: dict[str, Any]) -> Reply:
        reply = self.post("/api/projects/{projekt}/commands", {"command": command})
        if reply.status == 200:
            self.view = reply.json
        return reply

    @property
    def project(self) -> Any:
        assert self.view, "Es ist kein Projekt geladen"
        return self.view["project"]

    @property
    def answer_text(self) -> str:
        return "".join(str(e.get("delta") or "") for e in self.events if e["type"] == "text-delta")

    @property
    def tool_calls(self) -> list[str]:
        return [
            str(e.get("toolName"))
            for e in self.events
            if e["type"] in ("tool-input-available", "tool-input-start")
        ]

"""Offline token benchmark of the agent (``task bench``).

Replays fixed, realistic tool-call sequences through the real agent, tools and engine with a
scripted model and meters every model request (see ``metering``). No network, no API key, fully
deterministic: the numbers only change when prompts, tool definitions, tool outputs or history
handling change. Results are written as JSON and Markdown to ``docs/ai/benchmarks``.

    uv run python -m homeworking.modules.agent.bench --label baseline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from calc_engine.assembly.templates import template
from homeworking.bootstrap import Container, build_container
from homeworking.modules.agent.metering import Meter, tokens, tool_definitions_json
from homeworking.modules.agent.routing import route
from homeworking.modules.agent.tools import AgentDeps, build_agent
from homeworking.settings import Settings

# A realistic "Warum so?" explanation (prompt rule 5 asks for 4-6 paragraphs).
EXPLANATION = "\n\n".join(
    [
        "Bauweise: Das Regal ist als stabiler Korpus aus zwei Seitenwänden und eingelegten "
        "Böden aufgebaut. So tragen die Seiten die Last direkt in den Boden ab und die Böden "
        "steifen den Korpus gegen seitliches Verschieben aus.",
        "Material: Leimholz aus Fichte in 18 mm ist leicht, formstabil und preiswert. Für "
        "höhere Lasten wäre Multiplex eine Alternative, es ist aber teurer und schwerer.",
        "Verbindungen: Die Böden werden stumpf zwischen die Seiten gesetzt und von außen "
        "verschraubt. Zwei Schrauben je Ende verhindern das Verdrehen der Böden.",
        "Beschläge: Eine Rückwand aus dünner Platte verhindert das Parallelogramm-Kippen. "
        "Zusätzlich sollte das Regal oben an der Wand gesichert werden.",
        "Oberfläche: Ein farbloses Hartwachsöl schützt das Holz vor Flecken und lässt die "
        "Maserung sichtbar. Innen genügt ein Anstrich, Kanten zweimal behandeln.",
    ]
)
FINAL_ANSWER = (
    "Ich habe dein Regal geplant. Es ist 80 cm breit, 30 cm tief und 180 cm hoch und hat fünf "
    "Böden. Die Materialkosten liegen laut Engine im angezeigten Bereich. Rechts findest du "
    "Zeichnungen, Materialliste und Zuschnitt. Unter „Warum so?“ erkläre ich die Konstruktion. "
    "Möchtest du eine andere Holzart oder eine Rückwand?"
)

Step = Callable[[list[ModelMessage]], ModelResponse]


def _calls(*calls: tuple[str, dict[str, Any]]) -> Step:
    return lambda _messages: ModelResponse(parts=[ToolCallPart(n, a) for n, a in calls])


def _text(text: str) -> Step:
    return lambda _messages: ModelResponse(parts=[TextPart(text)])


def _broken_design(shift_mm: int) -> dict[str, Any]:
    """The shelf template moved below the floor: the engine rejects it with several errors."""
    design = template("shelf").design.model_dump(mode="json", exclude_defaults=True)
    for part in design["parts"]:
        x, y, z = part["at"]
        part["at"] = [x, y, f"({z}) - {shift_mm}"]
    design["object_type"] = "Regal"
    return design


def _valid_design() -> dict[str, Any]:
    design = template("shelf").design.model_dump(mode="json", exclude_defaults=True)
    design["object_type"] = "Regal"
    return design


@dataclass(frozen=True)
class Tools:
    """Tool names used by the scripts (kept in one place for prompt/tool refactorings)."""

    design: str = "save_design"


TOOLS = Tools()


def free_design_turn() -> list[Step]:
    """Free design: look up materials and an example, two engine rejections, then accepted."""
    args = {"title": "Wandregal", "params": {"width_mm": 800}, "explanation": EXPLANATION}
    return [
        _calls(("list_materials", {}), ("get_template_design", {"template_key": "shelf"})),
        _calls((TOOLS.design, {**args, "design": _broken_design(60)})),
        _calls((TOOLS.design, {**args, "design": _broken_design(20)})),
        _calls((TOOLS.design, {**args, "design": _valid_design()})),
        _text(FINAL_ANSWER),
    ]


def pack_turn() -> list[Step]:
    params = {"length_mm": 2000, "width_mm": 1000, "height_mm": 800, "wood": "larch"}
    return [
        _calls(
            (
                "create_project",
                {
                    "pack_id": "raised_bed",
                    "title": "Hochbeet",
                    "params": params,
                    "explanation": EXPLANATION,
                },
            )
        ),
        _text(FINAL_ANSWER),
    ]


def template_turn() -> list[Step]:
    params = {"width_mm": 800, "depth_mm": 300, "height_mm": 1800, "shelves": 5}
    return [
        _calls(
            (
                "create_from_template",
                {
                    "template_key": "shelf",
                    "title": "Regal",
                    "params": params,
                    "explanation": EXPLANATION,
                },
            )
        ),
        _text(FINAL_ANSWER),
    ]


def change_turn(command: dict[str, Any]) -> list[Step]:
    return [
        _calls(("change_project", {"command": command})),
        _text("Erledigt, die neuen Werte siehst du rechts im Projekt."),
    ]


def _script(steps: Sequence[Step]) -> Callable[[list[ModelMessage], AgentInfo], ModelResponse]:
    queue = list(steps)

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return queue.pop(0)(messages) if queue else ModelResponse(parts=[TextPart("Fertig.")])

    return respond


class Bench:
    def __init__(self, container: Container) -> None:
        self.container = container
        self.results: dict[str, dict[str, Any]] = {}

    async def turn(
        self,
        name: str,
        prompt: str,
        steps: Sequence[Step],
        deps: AgentDeps,
        history: list[ModelMessage] | None = None,
    ) -> list[ModelMessage]:
        meter = Meter()
        agent = build_agent(FunctionModel(meter.wrap(_script(steps))), self.container.engine)
        result = await agent.run(prompt, deps=deps, message_history=history)
        routed = route(prompt, has_project=deps.project_id is not None)
        self.results[name] = {**meter.totals(), "role": routed.role}
        return result.all_messages()

    async def prefix_breakdown(self) -> dict[str, Any]:
        """Estimated tokens of the static prefix: instructions and every tool definition."""
        seen: list[AgentInfo] = []

        def capture(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            seen.append(info)
            return ModelResponse(parts=[TextPart("ok")])

        deps = AgentDeps(
            owner_id=uuid4(), projects=self.container.projects, project_id=None, trace_id="b"
        )
        await build_agent(FunctionModel(capture), self.container.engine).run("x", deps=deps)
        info = seen[0]
        tools = {t.name: tokens(len(tool_definitions_json([t]))) for t in info.function_tools}
        return {
            "instructions": tokens(len(info.instructions or "")),
            "tools_total": tokens(len(tool_definitions_json(info.function_tools))),
            "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1])),
        }

    async def run(self) -> dict[str, dict[str, Any]]:
        self.results["prefix"] = await self.prefix_breakdown()
        owner = (await self.container.identity.create_guest()).id

        def deps() -> AgentDeps:
            return AgentDeps(
                owner_id=owner, projects=self.container.projects, project_id=None, trace_id="b"
            )

        await self.turn("pack_create", "Hochbeet 2 × 1 m, 80 cm hoch, Lärche", pack_turn(), deps())
        await self.turn("template_create", "Regal 80 × 30 × 180 cm", template_turn(), deps())

        free = deps()
        # Follow-up turns get the stored model messages of earlier runs as history, like the
        # chat endpoint (the baseline measured the browser re-sending its UI messages).
        history = await self.turn(
            "free_design", "Wandregal für Bücher, 80 cm breit", free_design_turn(), free
        )
        # The script relies on two engine rejections before acceptance.
        self.results["free_design"]["design_attempts"] = [
            a["accepted"] for a in free.design_attempts
        ]
        follow = AgentDeps(
            owner_id=owner,
            projects=self.container.projects,
            project_id=free.project_id,
            trace_id="b",
        )
        history = await self.turn(
            "followup_1",
            "Mach es 20 cm breiter",
            change_turn({"type": "change_parameter_by", "name": "width_mm", "delta": 200}),
            follow,
            history,
        )
        await self.turn(
            "followup_2",
            "Und bitte 10 cm höher",
            change_turn({"type": "change_parameter_by", "name": "height_mm", "delta": 100}),
            follow,
            history,
        )
        return self.results


async def run_bench() -> dict[str, dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{Path(tmp) / 'bench.db'}",
            llm_mode="test",
        )
        container = build_container(settings)
        await container.create_schema()
        try:
            return await Bench(container).run()
        finally:
            await container.close()


def markdown(label: str, results: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"# Token benchmark: {label}",
        "",
        "| Scenario | Requests | Prefix tok/request | Input tok | Output tok | Max request tok "
        "| Prefix share |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    scenarios = {k: v for k, v in results.items() if k not in ("prefix", "costs_usd")}
    for name, r in scenarios.items():
        lines.append(
            f"| {name} | {r['requests']} | {r['prefix_tokens_per_request']} | "
            f"{r['input_tokens']} | {r['output_tokens']} | {r['max_request_input_tokens']} | "
            f"{r['prefix_share']:.0%} |"
        )
    total_in = sum(r["input_tokens"] for r in scenarios.values())
    total_out = sum(r["output_tokens"] for r in scenarios.values())
    lines += ["", f"Total: {total_in} input / {total_out} output tokens (estimated, offline)."]
    prefix = results["prefix"]
    lines += [
        "",
        f"Static prefix: instructions {prefix['instructions']} tok, "
        f"tool definitions {prefix['tools_total']} tok.",
        "",
        "| Tool | Definition tok |",
        "|---|---:|",
        *(f"| {name} | {tok} |" for name, tok in prefix["tools"].items()),
    ]
    return "\n".join(lines) + "\n"


def request_cost(request: dict[str, int], price: dict[str, float], cached: bool) -> float:
    """USD of one request; with ``cached`` the static prefix is billed at the cache price."""
    prefix = tokens(request["instructions"] + request["tools"])
    rest = tokens(request["history"])
    output = tokens(request["output"])
    cache_price = price.get("cache_read")
    if cached and cache_price is not None:
        cost = prefix * cache_price + rest * price["input"]
    else:
        cost = (prefix + rest) * price["input"]
    return (cost + output * price["output"]) / 1_000_000


def costs(results: dict[str, dict[str, Any]], prices: dict[str, Any]) -> dict[str, Any]:
    """Cost per scenario and model configuration (prefix cached after a scenario's 1st call)."""
    models = prices["models"]
    out: dict[str, Any] = {}
    for config, roles in prices["configurations"].items():
        per_scenario = {}
        for name, r in results.items():
            if name == "prefix":
                continue
            price = models[roles[r["role"]]]
            per_scenario[name] = sum(
                request_cost(req, price, cached=i > 0) for i, req in enumerate(r["per_request"])
            )
        # One engine rejection = one more designer request of the size of a repair request.
        repair = results["free_design"]["per_request"][2]
        out[config] = {
            "scenarios": per_scenario,
            "total": sum(per_scenario.values()),
            "per_repair_round": request_cost(repair, models[roles["designer"]], cached=True),
        }
    return out


def cost_markdown(table: dict[str, Any]) -> str:
    scenarios = list(next(iter(table.values()))["scenarios"])
    lines = [
        "| Configuration | " + " | ".join(scenarios) + " | Total | +1 repair round |",
        "|---|" + "---:|" * (len(scenarios) + 2),
    ]
    for config, c in table.items():
        cells = [f"{c['scenarios'][s] * 100:.3f}" for s in scenarios]
        lines.append(
            f"| {config} | "
            + " | ".join(cells)
            + f" | {c['total'] * 100:.3f} | {c['per_repair_round'] * 100:.3f} |"
        )
    return "\n".join(
        ["", "Cost in US cents per scenario (offline token counts × list prices):", "", *lines]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="current")
    parser.add_argument("--out", type=Path, default=Path("docs/ai/benchmarks"))
    parser.add_argument("--prices", type=Path, default=Path("docs/ai/models.json"))
    args = parser.parse_args()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    results = asyncio.run(run_bench())
    report = markdown(args.label, results)
    if args.prices.exists():
        table = costs(results, json.loads(args.prices.read_text(encoding="utf-8")))
        results["costs_usd"] = table
        report += cost_markdown(table) + "\n"
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{date.today().isoformat()}-{args.label}"
    stem.with_suffix(".json").write_text(json.dumps(results, indent=2) + "\n")
    stem.with_suffix(".md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()

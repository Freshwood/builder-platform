"""One-off export of golden files from the Python engine for the Go port (ADR-0009).

Writes ``backend/testdata/golden/*.jsonl.gz``. Every line is one case with its inputs and what the
Python implementation produced, so the Go tests can compare exactly:

- ``engine.jsonl.gz``: ProjectInputs -> ConstructionResult or the rejection errors. Sources are the
  design corpus, the fixture and offline designs, the regression goldens and every ``Engine.build``
  / ``Engine.validate_design`` call made while the Python test suites run.
- ``expr.jsonl.gz``: expression + environment -> value or error message (all calls seen).
- ``svg.jsonl.gz``: drawing IR + element id -> SVG text.
- ``prompt.json``: instructions and tool definitions as the provider receives them.

Run with ``uv run python apps/api/scripts/export_goldens.py``. Deleted together with the Python code.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "backend" / "testdata" / "golden"
CAPTURE = OUT / "_capture"


def _key(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Sink:
    """Deduplicating JSON-lines writer."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.seen: set[str] = set()
        self.rows: list[dict[str, Any]] = []

    def add(self, key_obj: Any, row: dict[str, Any]) -> None:
        key = _key(key_obj)
        if key in self.seen:
            return
        self.seen.add(key)
        self.rows.append(row)

    def load(self, path: Path, key: str) -> None:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            self.add(row[key], row)

    def write(self) -> None:
        with gzip.open(self.path, "wt", encoding="utf-8") as fh:
            for row in self.rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"{self.path.relative_to(ROOT)}: {len(self.rows)} cases")


def _result(inputs: Any) -> dict[str, Any]:
    from calc_engine.engine import DesignRejectedError, default_engine

    try:
        result = default_engine().build(inputs)
    except DesignRejectedError as exc:
        return {"errors": exc.errors}
    return {"result": result.model_dump(mode="json")}


def explicit_cases(engine_sink: Sink, svg_sink: Sink) -> None:
    sys.path.insert(0, str(ROOT / "packages" / "calc-engine" / "tests"))
    from corpus import cases

    from construction_model.assembly import AssemblyDesign
    from construction_model.model import ProjectInputs
    from homeworking.modules.drawings.svg import render_svg

    def add(name: str, inputs: ProjectInputs, svgs: bool) -> None:
        dumped = inputs.model_dump(mode="json")
        out = _result(inputs)
        engine_sink.add(dumped, {"name": name, "inputs": dumped, **out})
        if svgs and "result" in out:
            result = __import__("calc_engine.engine", fromlist=["x"]).default_engine().build(inputs)
            for drawing in result.drawings:
                element_id = f"drawing-{drawing.view}"
                ir = drawing.model_dump(mode="json")
                svg_sink.add(
                    [ir, element_id],
                    {
                        "name": f"{name}/{drawing.view}",
                        "drawing": ir,
                        "element_id": element_id,
                        "svg": render_svg(drawing, element_id=element_id),
                    },
                )

    for i, case in enumerate(cases()):
        inputs = ProjectInputs(title=case.name, params=dict(case.params), design=case.design)
        # SVGs for every eighth case keep the file small but cover every design family.
        add(f"corpus/{case.name}", inputs, svgs=i % 8 == 0)

    design_dirs = {
        "fixture": ROOT / "packages" / "calc-engine" / "tests" / "fixtures" / "designs",
        "offline": ROOT / "apps" / "api" / "src" / "homeworking" / "modules" / "agent" / "offline_designs",
    }
    for source, directory in design_dirs.items():
        for path in sorted(directory.glob("*.json")):
            design = AssemblyDesign.model_validate_json(path.read_text(encoding="utf-8"))
            add(f"{source}/{path.stem}", ProjectInputs(title=path.stem, design=design, params={}), svgs=True)

    for case_dir in sorted((ROOT / "apps" / "api" / "tests" / "regressions").iterdir()):
        golden = case_dir / "golden.json"
        if not golden.exists():
            continue
        raw = json.loads(golden.read_text(encoding="utf-8"))
        case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        design = AssemblyDesign.model_validate(raw.get("design", raw))
        params = (case.get("golden") or {}).get("params") or {}
        add(f"regression/{case_dir.name}", ProjectInputs(title=case_dir.name, design=design, params=params), svgs=True)


def captured_cases(engine_sink: Sink, expr_sink: Sink, svg_sink: Sink) -> None:
    """Run the Python test suites with the capture plugin and merge what it saw."""
    CAPTURE.mkdir(parents=True, exist_ok=True)
    for f in CAPTURE.glob("*.jsonl"):
        f.unlink()
    plugin_dir = Path(__file__).resolve().parent
    env = {
        **__import__("os").environ,
        "PYTHONPATH": str(plugin_dir),
        "GOLDEN_CAPTURE_DIR": str(CAPTURE),
    }
    subprocess.run(
        ["uv", "run", "pytest", "-q", "-x", "-p", "golden_capture", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    engine_sink.load(CAPTURE / "engine.jsonl", "inputs")
    for line in (CAPTURE / "expr.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        expr_sink.add([row["expr"], row["env"], row["fn"]], row)
    for line in (CAPTURE / "svg.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        svg_sink.add([row["drawing"], row["element_id"]], row)


def prompt() -> None:
    from homeworking.modules.agent.prompts import PROMPT_VERSION
    from homeworking.modules.agent.provenance import prompt_spec

    spec = asyncio.run(prompt_spec())
    data = {"version": PROMPT_VERSION, "fingerprint": spec.fingerprint, **spec.canonical()}
    (OUT / "prompt.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("backend/testdata/golden/prompt.json")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    engine_sink = Sink(OUT / "engine.jsonl.gz")
    expr_sink = Sink(OUT / "expr.jsonl.gz")
    svg_sink = Sink(OUT / "svg.jsonl.gz")
    explicit_cases(engine_sink, svg_sink)
    captured_cases(engine_sink, expr_sink, svg_sink)
    engine_sink.write()
    expr_sink.write()
    svg_sink.write()
    prompt()
    for f in CAPTURE.glob("*.jsonl"):
        f.unlink()
    CAPTURE.rmdir()


if __name__ == "__main__":
    main()

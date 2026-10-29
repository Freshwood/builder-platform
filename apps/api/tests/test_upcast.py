"""Projects stored before ADR-0008 (schema 1, pack "design") still load and replay."""

from typing import Any
from uuid import uuid4

from api_designs import design
from homeworking.calc_engine.engine import default_engine
from homeworking.construction_model.commands import CreateProject, ReplaceInputs, command_adapter
from homeworking.construction_model.model import ProjectInputs, ProjectModel
from homeworking.modules.projects.repository import load_command, load_model


def _schema_1(model: ProjectModel) -> dict[str, Any]:
    """The document as it was stored before packs and templates were removed."""
    document = model.model_dump(mode="json")
    document["schema_version"] = 1
    document["inputs"]["pack_id"] = "design"
    document["result"]["trust"] = "ai_draft"
    provenance = document["result"]["provenance"]
    del provenance["design_version"]
    provenance |= {"pack_id": "design", "pack_version": "1.1.0"}
    return document


def test_schema_1_design_project_is_upcast() -> None:
    inputs = ProjectInputs(title="Beet", design=design("raised_bed"), params={})
    model = ProjectModel(id=uuid4(), inputs=inputs, result=default_engine().build(inputs))

    loaded = load_model(_schema_1(model))

    assert loaded.schema_version == 2
    assert loaded.inputs == model.inputs
    assert loaded.result.provenance.design_version == "1.1.0"


def test_schema_1_commands_are_upcast() -> None:
    created = command_adapter.dump_python(
        CreateProject(title="Beet", design=design("raised_bed")), mode="json"
    )
    assert isinstance(load_command({**created, "pack_id": "design"}), CreateProject)

    inputs = ProjectInputs(title="Beet", design=design("raised_bed"), params={})
    replaced = command_adapter.dump_python(ReplaceInputs(inputs=inputs), mode="json")
    replaced["inputs"]["pack_id"] = "design"
    loaded = load_command(replaced)
    assert isinstance(loaded, ReplaceInputs)
    assert loaded.inputs == inputs

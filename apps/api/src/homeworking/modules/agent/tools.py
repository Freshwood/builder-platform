"""Agent definition. Tools translate LLM intents into typed project commands.

The tools live in ``design_tools.py`` (designs) and ``project_tools.py`` (the open project), the
per-turn state in ``deps.py``, the observers in ``capabilities.py``.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.models import Model

from homeworking.modules.agent.args import RepairToolArgs
from homeworking.modules.agent.capabilities import (
    RecordRequestShape,
    RecordToolAttempts,
    RecordUsage,
)
from homeworking.modules.agent.deps import AgentDeps
from homeworking.modules.agent.design_tools import register_design_tools
from homeworking.modules.agent.history import process_history
from homeworking.modules.agent.project_tools import register_project_tools
from homeworking.modules.agent.prompts import INSTRUCTIONS


def build_agent(model: Model) -> Agent[AgentDeps, str]:
    agent: Agent[AgentDeps, str] = Agent(
        model,
        deps_type=AgentDeps,
        instructions=INSTRUCTIONS,
        retries=2,
        capabilities=[
            ProcessHistory(process_history),
            RepairToolArgs(),
            RecordToolAttempts(),
            RecordUsage(),
            RecordRequestShape(),
        ],
    )
    # The order is part of the fingerprint: design tools first, then the project tools.
    register_design_tools(agent)
    register_project_tools(agent)
    return agent

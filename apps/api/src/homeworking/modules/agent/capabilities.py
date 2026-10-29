"""pydantic-ai capabilities of the chat agent: they observe every model request and tool call and
keep what a failed run needs to be diagnosed (usage, request shape, raw tool arguments)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from pydantic_ai import AgentRunResult, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability, WrapModelRequestHandler
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import ToolDefinition

from homeworking.modules.agent.deps import AgentDeps, tool_attempt
from homeworking.modules.agent.request_shape import error_info, request_shape


@dataclass
class RecordUsage(AbstractCapability[AgentDeps]):
    """Store tokens and the provider's resolved model name of every model response."""

    async def after_model_request(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        response: ModelResponse,
    ) -> ModelResponse:
        usage = response.usage
        ctx.deps.requests.append(
            {
                "model": response.model_name,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_tokens": usage.cache_read_tokens,
            }
        )
        return response

    @classmethod
    def get_serialization_name(cls) -> str | None:
        return None


@dataclass
class RecordRequestShape(AbstractCapability[AgentDeps]):
    """Keep the structure of every model request as sent, and of the error if the call fails.

    ``wrap_model_request`` sees the final messages (after history processing and the framework's
    clean-up), i.e. what the model class maps to the provider array. Observing only: the request
    is passed on unchanged, and a failure while recording never breaks the run.
    """

    async def wrap_model_request(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        deps = ctx.deps
        deps.request_count += 1
        number = deps.request_count
        try:
            deps.last_request_shape = await request_shape(request_context, number)
        except Exception:  # diagnostics must never break a run
            deps.last_request_shape = None
        deps.request_open = number
        try:
            response = await handler(request_context)
        except Exception as error:
            self._remember(deps, number, error)
            raise
        deps.request_open = None
        return response

    async def on_model_request_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        error: Exception,
    ) -> ModelResponse:
        self._remember(ctx.deps, ctx.deps.request_count, error)
        raise error

    async def on_run_error(
        self, ctx: RunContext[AgentDeps], *, error: BaseException
    ) -> AgentRunResult[Any]:
        """A streamed request opens lazily: its provider error surfaces here, not in the hooks above.

        (``wrap_run_event_stream`` would see it too, but defining it makes ``agent.run`` stream.)
        Only a run that died while a request was in flight counts as a failed model call.
        """
        deps = ctx.deps
        known = (deps.last_request_error or {}).get("request_number")
        if deps.request_open is not None and known != deps.request_open:
            self._remember(deps, deps.request_open, error)
        raise error

    @staticmethod
    def _remember(deps: AgentDeps, number: int, error: BaseException) -> None:
        # ModelRetry is a retry request of the framework, not a failure of the call.
        if isinstance(error, ModelRetry):
            return
        deps.last_request_error = {"request_number": number, **error_info(error)}

    @classmethod
    def get_serialization_name(cls) -> str | None:
        return None


def _validation_messages(error: ValidationError | ModelRetry) -> list[str]:
    """Compact texts of an argument error (location, message, type); no input echo."""
    if isinstance(error, ModelRetry):
        return [str(error.message)]
    return [
        f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']} [{e['type']}]"
        for e in error.errors(include_url=False, include_input=False, include_context=False)
    ]


@dataclass
class RecordToolAttempts(AbstractCapability[AgentDeps]):
    """Keep the raw arguments of every tool call and record calls that fail validation.

    Failures inside a tool body are recorded there (``_attempt``, ``_fail``); this capability
    covers what never reaches the body: schema violations (e.g. an extra key inside ``design``),
    JSON that cannot be repaired (``RepairToolArgs``) and unexpected exceptions.
    """

    async def before_tool_validate(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: str | dict[str, Any],
    ) -> str | dict[str, Any]:
        ctx.deps.raw_tool_args[call.tool_call_id] = args
        return args

    async def on_tool_validate_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: str | dict[str, Any],
        error: ValidationError | ModelRetry,
    ) -> dict[str, Any]:
        ctx.deps.design_attempts.append(
            tool_attempt(
                tool=call.tool_name,
                tool_call_id=call.tool_call_id,
                outcome="invalid_args",
                errors=_validation_messages(error),
                raw_args=args,
            )
        )
        raise error

    async def on_tool_execute_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        error: Exception,
    ) -> Any:
        ctx.deps.design_attempts.append(
            tool_attempt(
                tool=call.tool_name,
                tool_call_id=call.tool_call_id,
                outcome="exception",
                errors=[f"{type(error).__name__}: {error}"[:2000]],
                raw_args=ctx.deps.raw_tool_args.get(call.tool_call_id),
            )
        )
        raise error

    @classmethod
    def get_serialization_name(cls) -> str | None:
        return None

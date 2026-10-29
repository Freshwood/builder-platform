"""Blocking work off the event loop.

One mechanism for everything that is not a request handler (engine builds, merging modules, PDF
warm-up): ``anyio.to_thread``, the same one FastAPI's ``run_in_threadpool`` uses. Route handlers
call ``run_in_threadpool`` themselves (AGENTS.md); anything below them uses ``run_blocking``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVarTuple

import anyio.to_thread

Args = TypeVarTuple("Args")


async def run_blocking[T, *Args](
    func: Callable[[*Args], T], *args: *Args, abandon_on_cancel: bool = False
) -> T:
    """Run ``func(*args)`` in a worker thread and wait for it.

    ``abandon_on_cancel``: a cancelled caller stops waiting at once instead of after the thread
    finished (the thread itself cannot be stopped)."""
    return await anyio.to_thread.run_sync(func, *args, abandon_on_cancel=abandon_on_cancel)

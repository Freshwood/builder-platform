"""``run_blocking``: the one way non-handler code leaves the event loop."""

import asyncio
import threading
import time

import pytest

from homeworking.concurrency import run_blocking


async def test_the_function_runs_in_a_worker_thread_with_its_arguments() -> None:
    def where(a: int, b: int) -> tuple[int, int]:
        return a + b, threading.get_ident()

    total, thread = await run_blocking(where, 1, 2)
    assert total == 3
    assert thread != threading.get_ident()


async def test_the_event_loop_stays_responsive_while_the_work_blocks() -> None:
    ticks: list[int] = []

    async def ticker() -> None:
        for i in range(3):
            ticks.append(i)
            await asyncio.sleep(0.01)

    await asyncio.gather(run_blocking(time.sleep, 0.1), ticker())
    assert ticks == [0, 1, 2]


async def test_an_exception_of_the_work_reaches_the_caller() -> None:
    def broken() -> None:
        raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        await run_blocking(broken)


async def test_a_cancelled_caller_can_stop_waiting_at_once() -> None:
    release = threading.Event()
    task = asyncio.create_task(run_blocking(release.wait, 5.0, abandon_on_cancel=True))
    await asyncio.sleep(0.01)
    task.cancel()
    started = time.perf_counter()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    assert time.perf_counter() - started < 1

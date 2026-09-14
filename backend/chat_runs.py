"""Explicit cancellation for one app-owned chat, including request preparation."""
import asyncio
from dataclasses import dataclass, field

@dataclass
class Run:
    task: asyncio.Task | None = None
    cancelled: bool = False
    done: asyncio.Event = field(default_factory=asyncio.Event)

runs: dict[tuple[str, str], Run] = {}

async def stop(key):
    run = runs.get(key)
    if run is None:
        return True
    run.cancelled = True
    if run.task and not run.task.done():
        run.task.cancel()
    try:
        await asyncio.wait_for(run.done.wait(), timeout=15)
    except asyncio.TimeoutError:
        return False
    return True

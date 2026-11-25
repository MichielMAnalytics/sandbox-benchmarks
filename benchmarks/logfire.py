"""Logfire Agent Sandboxes, opening a session at each checkout.

Run with `uv run -m benchmarks.logfire [n] [--save LOCATION]`; see `main` in shared.py.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Self

import logfire

from .shared import Functions, Pool, Session, main


class LogfireSession(Session):
    def __init__(self, session: Any):
        self.session = session

    async def feed_run(self, code: str, external_lookup: Functions | None = None) -> Any:
        return await self.session.feed_run(code, external_lookup=external_lookup)


class LogfirePool(Pool):
    """`pre_warm` is the number of sessions to keep open ahead of each checkout."""

    def __init__(self, pre_warm: int = 0):
        self.remote = logfire.agent_sandboxes(pre_warm=pre_warm)

    async def __aenter__(self) -> Self:
        await self.remote.__aenter__()
        await asyncio.sleep(3)  # let a pre-warmed pool fill
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.remote.__aexit__(*args)

    @asynccontextmanager
    async def checkout(self) -> AsyncIterator[LogfireSession]:
        async with self.remote.checkout() as session:
            yield LogfireSession(session)


if __name__ == '__main__':
    main('logfire', 'Logfire', LogfirePool())

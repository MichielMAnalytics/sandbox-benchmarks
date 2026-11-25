"""Logfire Agent Sandboxes, opening a session at each checkout.

Run with `uv run -m benchmarks.logfire [n] [--save LOCATION]`; see `main` in shared.py.

Design decisions
----------------

`feed_run(code, external_lookup={...})` is part of the API. The code runs in Monty
(https://github.com/pydantic/monty), which stops at a call to an external function and hands it to the host,
so nothing passes through JSON or stdout: in our tests tuples, `bytes`, sets, datetimes and integer dict keys
arrived with their types, and a `ValueError` raised on the host was caught as one in the sandbox. The cost is
that Monty is not CPython. It runs a subset of Python with few of the standard library's modules and no
third-party packages, and the hosted service stopped a feed that computed for more than 50ms, not counting
time waiting on the host.

`logfire_turbo.py` is the same pool with `pre_warm=5`, which keeps a buffer of sessions ready to use at
checkout.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Self

import logfire

from .shared import Functions, Pool, Session, main

URL = 'https://pydantic.dev/docs/logfire/agent-sandboxes/'


class LogfireSession(Session):
    def __init__(self, session: Any):
        self.session = session

    async def run(self, code: str) -> str:
        printed: list[str] = []
        await self.session.feed_run(code, print_callback=lambda _stream, text: printed.append(text))
        return ''.join(printed)

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
    main('logfire', 'Pydantic Logfire', URL, LogfirePool())

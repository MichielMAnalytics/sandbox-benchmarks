"""Modal: the REPL runs over the stdin and stdout of `sandbox.exec`.

Run with `uv run -m benchmarks.modal [n] [--save LOCATION]`; see `main` in shared.py.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import modal

from .shared import STDIO_REPL, Pool, StdioSession, main


class ModalSession(StdioSession):
    def __init__(self, process: Any):
        self.process = process
        self.lines = aiter(process.stdout)

    async def write(self, line: str) -> None:
        self.process.stdin.write(line)
        await self.process.stdin.drain.aio()

    async def readline(self) -> str:
        return await anext(self.lines)


class ModalPool(Pool):
    """Uses Modal's async interface (`.aio`), since its blocking one misbehaves inside an event loop."""

    def __init__(self) -> None:
        self.app: Any = None

    @asynccontextmanager
    async def checkout(self) -> AsyncIterator[ModalSession]:
        if self.app is None:
            self.app = await modal.App.lookup.aio('sandbox-benchmarks', create_if_missing=True)
        sandbox = await modal.Sandbox.create.aio(app=self.app)
        try:
            process = await sandbox.exec.aio('python', '-u', '-c', STDIO_REPL, bufsize=1)
            yield ModalSession(process)
        finally:
            await sandbox.terminate.aio()


if __name__ == '__main__':
    main('modal', 'Modal', ModalPool())

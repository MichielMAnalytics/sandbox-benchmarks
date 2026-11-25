"""Modal: the REPL runs over the stdin and stdout of `sandbox.exec`.

Run with `uv run -m benchmarks.modal [n] [--save LOCATION]`; see `main` in shared.py.

Design decisions
----------------

JSON lines over the stdin and stdout of `sandbox.exec`, which is how Modal's code interpreter example
(https://modal.com/docs/examples/simple_code_interpreter) drives a long-running process in a sandbox.

The protocol is JSON lines over the program's stdin and stdout, and the docstring of shared.py has what that
costs on every provider that uses it.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import modal

from .shared import STDIO_REPL, Pool, StdioSession, main


class ModalSession(StdioSession):
    def __init__(self, sandbox: Any):
        self.sandbox = sandbox
        self.process: Any = None
        self.lines: Any = None

    async def run(self, code: str) -> str:
        process = await self.sandbox.exec.aio('python', '-c', code)
        return await process.stdout.read.aio()

    async def start(self) -> None:
        self.process = await self.sandbox.exec.aio('python', '-u', '-c', STDIO_REPL, bufsize=1)
        self.lines = aiter(self.process.stdout)

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
            yield ModalSession(sandbox)
        finally:
            await sandbox.terminate.aio()


if __name__ == '__main__':
    main('modal', 'Modal', 'https://modal.com/docs/guide/sandboxes', ModalPool())

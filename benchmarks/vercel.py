"""Vercel Sandbox: the REPL runs over the stdin of a running command.

Run with `uv run -m benchmarks.vercel [n] [--save LOCATION]`; see `main` in shared.py.
"""

import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from vercel import sandbox

from .shared import STDIO_REPL, Pool, StdioSession, main


class VercelSession(StdioSession):
    def __init__(self, command: Any):
        self.command = command

    async def write(self, line: str) -> None:
        await self.command.stdin.send(line.encode())

    async def readline(self) -> str:
        return (await self.command.stdout.readline()).decode()


class VercelPool(Pool):
    @asynccontextmanager
    async def checkout(self) -> AsyncIterator[VercelSession]:
        # leaving the block stops and deletes the sandbox; persistent=False skips the snapshot it would take
        async with sandbox.create_sandbox(image='vercel/sandbox/python:3.15', persistent=False) as box:
            await box.fs.write_text('repl.py', STDIO_REPL)
            command = await box.create_command(
                'python3', ['-u', 'repl.py'], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            try:
                yield VercelSession(command)
            finally:
                # an output stream left open gives 'asynchronous generator is already running' at exit
                await command.stdout.aclose()


if __name__ == '__main__':
    main('vercel', 'Vercel', VercelPool())

"""Vercel Sandbox: the REPL runs over the stdin of a running command.

Run with `uv run -m benchmarks.vercel [n] [--save LOCATION]`; see `main` in shared.py.

Design decisions
----------------

JSON lines over the stdin of a running command, from the Python SDK reference
(https://vercel.com/docs/sandbox/sdk/python). Each line written to stdin is an HTTPS request of its own, about
200ms from London, which is most of what a call costs.

The protocol is JSON lines over the program's stdin and stdout, and the docstring of shared.py has what that
costs on every provider that uses it. Vercel's docs have nothing on calling functions on the host: the page
linked above only documents writing to the stdin of a running command, which is what we send those JSON lines
over.
"""

import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from vercel import sandbox

from .shared import STDIO_REPL, Pool, StdioSession, main


class VercelSession(StdioSession):
    def __init__(self, box: Any):
        self.box = box
        self.command: Any = None

    async def run(self, code: str) -> str:
        done = await self.box.run_command('python3', ['-c', code], capture_output=True)
        return done.stdout.decode()

    async def start(self) -> None:
        await self.box.fs.write_text('repl.py', STDIO_REPL)
        self.command = await self.box.create_command(
            'python3', ['-u', 'repl.py'], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
        )

    async def write(self, line: str) -> None:
        await self.command.stdin.send(line.encode())

    async def readline(self) -> str:
        return (await self.command.stdout.readline()).decode()


class VercelPool(Pool):
    @asynccontextmanager
    async def checkout(self) -> AsyncIterator[VercelSession]:
        # leaving the block stops and deletes the sandbox; persistent=False skips the snapshot it would take
        async with sandbox.create_sandbox(image='vercel/sandbox/python:3.15', persistent=False) as box:
            session = VercelSession(box)
            try:
                yield session
            finally:
                # an output stream left open gives 'asynchronous generator is already running' at exit
                if session.command is not None:
                    await session.command.stdout.aclose()


if __name__ == '__main__':
    main('vercel', 'Vercel', 'https://vercel.com/docs/sandbox', VercelPool())

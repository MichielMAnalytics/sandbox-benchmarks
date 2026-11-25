"""E2B: the REPL runs as a background command, fed with `send_stdin`.

Run with `uv run -m benchmarks.e2b [n] [--save LOCATION]`; see `main` in shared.py.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

from e2b import Sandbox

from .shared import STDIO_REPL, Pool, StdioSession, main


class E2BSession(StdioSession):
    def __init__(self, command: Any):
        self.command = command
        self.lines = self.read_lines()

    def read_lines(self) -> Iterator[str]:
        buffer = ''
        for stdout, _stderr, _pty in self.command:
            buffer += stdout or ''
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                yield line

    async def write(self, line: str) -> None:
        self.command.send_stdin(line)

    async def readline(self) -> str:
        return next(self.lines)


class E2BPool(Pool):
    @asynccontextmanager
    async def checkout(self) -> AsyncIterator[E2BSession]:
        sandbox = Sandbox.create()
        try:
            sandbox.files.write('/home/user/repl.py', STDIO_REPL)
            # `run_code` has no way to send anything back to running code, so this has to be a command with stdin
            command = sandbox.commands.run('python3 -u /home/user/repl.py', background=True, stdin=True, timeout=0)
            yield E2BSession(command)
        finally:
            sandbox.kill()


if __name__ == '__main__':
    main('e2b', 'E2B', E2BPool())

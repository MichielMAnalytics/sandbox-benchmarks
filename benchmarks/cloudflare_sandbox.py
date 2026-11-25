"""Cloudflare sandboxes: the REPL runs over a WebSocket to the Worker in cloudflare_sandbox/.

Run with `uv run -m benchmarks.cloudflare_sandbox [n] [--save LOCATION]`; see `main` in shared.py.
"""

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from websockets.asyncio.client import connect

from .shared import STDIO_REPL, Pool, StdioSession, main


class CloudflareSandboxSession(StdioSession):
    def __init__(self, socket: Any):
        self.socket = socket
        self.buffer = ''

    async def write(self, line: str) -> None:
        await self.socket.send(line)

    async def readline(self) -> str:
        while '\n' not in self.buffer:
            self.buffer += await self.socket.recv()
        line, self.buffer = self.buffer.split('\n', 1)
        return line


class CloudflareSandboxPool(Pool):
    """Talks to the Worker in cloudflare_sandbox/, which gives each WebSocket a sandbox of its own."""

    @asynccontextmanager
    async def checkout(self) -> AsyncIterator[CloudflareSandboxSession]:
        url = f'{os.environ["CLOUDFLARE_SANDBOX_URL"]}/{uuid.uuid4()}'
        headers = {'Authorization': f'Bearer {os.environ["CLOUDFLARE_SANDBOX_KEY"]}'}
        # the Worker destroys the sandbox when the socket closes
        async with connect(url, additional_headers=headers, open_timeout=30) as socket:
            await socket.send(STDIO_REPL)
            yield CloudflareSandboxSession(socket)


if __name__ == '__main__':
    main('cloudflare_sandbox', 'Cloudflare sandbox', CloudflareSandboxPool())

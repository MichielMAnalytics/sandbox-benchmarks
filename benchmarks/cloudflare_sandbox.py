"""Cloudflare sandboxes: the REPL runs over a WebSocket to the Worker in cloudflare_sandbox/.

Run with `uv run -m benchmarks.cloudflare_sandbox [n] [--save LOCATION]`; see `main` in shared.py.

Design decisions
----------------

A sandbox can only be reached from a Worker, so you deploy the one in `cloudflare_sandbox/` and the JSON lines
travel over a WebSocket that it joins to the program's stdin and stdout, the arrangement Cloudflare shows for
a terminal in the browser
(https://developers.cloudflare.com/sandbox/commands/open-a-terminal-in-the-browser/). That Worker is a public
address that runs whatever program it is sent, guarded by one shared key, so the key needs the care of a
password. The container is destroyed when the socket closes, so a dropped connection ends the session.

The protocol is JSON lines over the program's stdin and stdout, and the docstring of shared.py has what that
costs on every provider that uses it. Cloudflare's docs have nothing on calling functions on the host: the
page linked above only documents joining a WebSocket to a process in the sandbox, which is what we send those
JSON lines over.
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

"""boat.dev: the REPL runs over `ssh`, since its commands have no stdin.

Run with `uv run -m benchmarks.boat [n] [--save LOCATION]`; see `main` in shared.py.

Design decisions
----------------

Its commands have no stdin, and its docs say to use SSH (https://docs.boat.dev/ssh-access) for piped input, so
the JSON lines go over `ssh`. Each session makes a new key pair and pins the host key it gets from the API. It
needs an `ssh` client and outbound access to the sandbox's SSH port, and opening the connection is part of
every session's time.

The protocol is JSON lines over the program's stdin and stdout, and the docstring of shared.py has what that
costs on every provider that uses it. boat.dev's docs have nothing on calling functions on the host: the page
linked above only documents connecting over SSH, which is what we send those JSON lines over.
"""

import asyncio
import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from boat_sdk import ApiClient, Configuration, exec_command, wait_until_ready, write_text
from boat_sdk.api.boat_api import BoatApi
from boat_sdk.models import CreateSandboxRequest, SshKeyRequest

from .shared import STDIO_REPL, Pool, StdioSession, main


def boat_ssh(boat: Any, sandbox_id: str, directory: str) -> list[str]:
    """Authorise a new key on a boat sandbox and return the `ssh` command that reaches it."""
    key = f'{directory}/key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', key], check=True)
    reply = boat.ssh_key(sandbox_id, SshKeyRequest(key=Path(f'{key}.pub').read_text().strip()))
    # the host key comes over the API, so it can be pinned without trusting the first connection
    Path(f'{directory}/known_hosts').write_text(f'{sandbox_id} {reply.host_key}\n')
    # ssh_endpoint is 'host:port', set when the sandbox has no public IPv4 address of its own
    host, port = reply.ssh_endpoint.rsplit(':', 1) if reply.ssh_endpoint else (reply.machine_ip, '22')
    # IdentitiesOnly, or ssh offers the agent's keys first and is refused for too many failures
    options = [
        'IdentitiesOnly=yes',
        'StrictHostKeyChecking=yes',
        f'UserKnownHostsFile={directory}/known_hosts',
        f'HostKeyAlias={sandbox_id}',
    ]
    return ['ssh', '-i', key, '-p', port, *(arg for o in options for arg in ('-o', o)), f'{reply.ssh_user}@{host}']


class BoatSession(StdioSession):
    def __init__(self, boat: BoatApi, sandbox_id: str):
        self.boat = boat
        self.sandbox_id = sandbox_id
        self.directory: str | None = None
        self.process: asyncio.subprocess.Process | None = None

    async def run(self, code: str) -> str:
        done: Any = exec_command(self.boat, self.sandbox_id, f'python3 -c {shlex.quote(code)}')
        return done.actual_instance.stdout

    async def start(self) -> None:
        write_text(self.boat, self.sandbox_id, 'repl.py', STDIO_REPL)
        self.directory = tempfile.mkdtemp()
        ssh = boat_ssh(self.boat, self.sandbox_id, self.directory)
        self.process = await asyncio.create_subprocess_exec(
            *ssh, 'python3', '-u', 'repl.py', stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )

    async def write(self, line: str) -> None:
        assert self.process and self.process.stdin
        self.process.stdin.write(line.encode())
        await self.process.stdin.drain()

    async def readline(self) -> str:
        assert self.process and self.process.stdout
        return (await self.process.stdout.readline()).decode()

    async def close(self) -> None:
        if self.process is not None:
            if self.process.returncode is None:
                self.process.kill()
            await self.process.wait()
        if self.directory is not None:
            shutil.rmtree(self.directory)


class BoatPool(Pool):
    """boat's commands have no stdin, so the REPL is run over `ssh`, as its docs say to for piped input."""

    def __init__(self) -> None:
        config = Configuration(host='https://boat.dev/api/v1', access_token=os.environ['BOAT_API_KEY'])
        self.boat = BoatApi(ApiClient(config))

    @asynccontextmanager
    async def checkout(self) -> AsyncIterator[BoatSession]:
        boat = self.boat
        sandbox_id = boat.create(create_sandbox_request=CreateSandboxRequest(ttl_seconds=600)).sandbox.id
        try:
            wait_until_ready(boat, sandbox_id, poll_interval_seconds=0.1)
            session = BoatSession(boat, sandbox_id)
            try:
                yield session
            finally:
                await session.close()
        finally:
            boat.delete_sandbox(sandbox_id=sandbox_id, x_ascii_confirm_delete=sandbox_id)


if __name__ == '__main__':
    main('boat', 'boat.dev', 'https://boat.dev', BoatPool())

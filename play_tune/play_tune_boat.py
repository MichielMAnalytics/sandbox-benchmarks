"""The same tune as play_tune.py, run in a boat.dev sandbox. Needs BOAT_API_KEY and `ssh` on this machine.

boat's commands have no stdin and its docs say to pipe input over SSH, so this follows
https://docs.boat.dev/ssh-access: the same stdin/stdout protocol as Modal and E2B, over `ssh`.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from boat_sdk import ApiClient, Configuration, wait_until_ready, write_text
from boat_sdk.api.boat_api import BoatApi
from boat_sdk.models import CreateSandboxRequest, SshKeyRequest

from play_tune import code, play, speakers

# there is no built-in way for code in the sandbox to call a function on this machine, so this goes at the
# top of the code: each call is written to stdout as a line of JSON, and the result is read from stdin
stub = """
import json, sys

def call(name, *args):
    print(json.dumps({"call": name, "args": args}), flush=True)
    reply = json.loads(sys.stdin.readline())
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"]

def play(note, seconds):
    return call("play", note, seconds)
"""

# the functions the sandbox may call
functions = {'play': play}


def run_call(line: str) -> str:
    request = json.loads(line)
    try:
        reply = {'result': functions[request['call']](*request['args'])}
    except Exception as e:
        reply = {'error': repr(e)}
    return json.dumps(reply) + '\n'


def ssh_command(boat: BoatApi, sandbox_id: str, directory: str) -> list[str]:
    """Authorise a new key on the sandbox and return the `ssh` command that reaches it."""
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


def main() -> None:
    config = Configuration(host='https://boat.dev/api/v1', access_token=os.environ['BOAT_API_KEY'])
    with ApiClient(config) as client, tempfile.TemporaryDirectory() as directory:
        boat = BoatApi(client)
        sandbox_id = boat.create(create_sandbox_request=CreateSandboxRequest(ttl_seconds=600)).sandbox.id
        try:
            wait_until_ready(boat, sandbox_id, poll_interval_seconds=0.2)
            write_text(boat, sandbox_id, 'tune.py', stub + code)
            ssh = ssh_command(boat, sandbox_id, directory)
            with (
                speakers,
                subprocess.Popen(
                    [*ssh, 'python3', '-u', 'tune.py'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
                ) as process,
            ):
                assert process.stdin and process.stdout
                # every line the code prints has to be a call, anything else breaks the protocol
                for line in process.stdout:
                    process.stdin.write(run_call(line))
                    process.stdin.flush()
        finally:
            boat.delete_sandbox(sandbox_id=sandbox_id, x_ascii_confirm_delete=sandbox_id)


if __name__ == '__main__':
    main()

"""The same tune as play_tune.py, run in a Cloudflare sandbox. Needs CLOUDFLARE_SANDBOX_URL and CLOUDFLARE_SANDBOX_KEY.

Cloudflare's sandboxes are only reachable from a Worker, so this talks to the one in cloudflare_sandbox/, which
passes a WebSocket through to the stdin and stdout of the program, as in
https://developers.cloudflare.com/sandbox/commands/open-a-terminal-in-the-browser/
"""

import json
import os
import uuid

from websockets.sync.client import connect

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


def main() -> None:
    # a new name gives a new sandbox, and the Worker destroys it when the socket closes
    url = f'{os.environ["CLOUDFLARE_SANDBOX_URL"]}/{uuid.uuid4()}'
    headers = {'Authorization': f'Bearer {os.environ["CLOUDFLARE_SANDBOX_KEY"]}'}
    with connect(url, additional_headers=headers) as socket, speakers:
        socket.send(stub + code)
        buffer = ''
        # every line the code prints has to be a call, anything else breaks the protocol
        for chunk in socket:
            buffer += chunk
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                socket.send(run_call(line))


if __name__ == '__main__':
    main()

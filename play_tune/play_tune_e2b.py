"""The same tune as play_tune.py, run in an E2B sandbox. Needs E2B_API_KEY.

Follows the stdin/stdout protocol of https://docs.e2b.dev/agents/dspy
"""

import json

from e2b import Sandbox

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
    with Sandbox.create() as sandbox, speakers:
        sandbox.files.write('/home/user/tune.py', stub + code)
        # `run_code` has no way to send anything back to running code, so this has to be a command with stdin
        command = sandbox.commands.run('python3 -u /home/user/tune.py', background=True, stdin=True, timeout=0)
        buffer = ''
        # every line the code prints has to be a call, anything else breaks the protocol
        for stdout, _stderr, _pty in command:
            buffer += stdout or ''
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                command.send_stdin(run_call(line))


if __name__ == '__main__':
    main()

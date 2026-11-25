"""The same tune as play_tune.py, run in a Vercel sandbox. Needs VERCEL_TOKEN, VERCEL_TEAM_ID and VERCEL_PROJECT_ID.

Follows the stdin of a running command in https://vercel.com/docs/sandbox/python-sdk-reference
"""

import json
import subprocess

from vercel.sandbox import sync as sandbox

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


def run_call(line: bytes) -> bytes:
    request = json.loads(line)
    try:
        reply = {'result': functions[request['call']](*request['args'])}
    except Exception as e:
        reply = {'error': repr(e)}
    return json.dumps(reply).encode() + b'\n'


def main() -> None:
    # leaving the `with` block stops and deletes the sandbox; persistent=False skips the snapshot it would take
    with sandbox.create_sandbox(image='vercel/sandbox/python:3.15', persistent=False) as box, speakers:
        box.fs.write_text('tune.py', stub + code)
        process = box.create_command('python3', ['-u', 'tune.py'], stdin=subprocess.PIPE)
        # every line the code prints has to be a call, anything else breaks the protocol
        for line in process.stdout:
            process.stdin.write(run_call(line))


if __name__ == '__main__':
    main()

"""The same tune as play_tune.py, run in a Modal sandbox. Needs `modal setup` to have been run.

Follows the stdin/stdout protocol of https://modal.com/docs/examples/simple_code_interpreter
"""

import json

import modal

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
    app = modal.App.lookup('play-tune', create_if_missing=True)
    sandbox = modal.Sandbox.create(app=app)
    try:
        with speakers:
            process = sandbox.exec('python', '-u', '-c', stub + code, bufsize=1)
            # every line the code prints has to be a call, anything else breaks the protocol
            for line in process.stdout:
                process.stdin.write(run_call(line))
                process.stdin.drain()
    finally:
        sandbox.terminate()


if __name__ == '__main__':
    main()

"""The same tune as play_tune.py, run in a Daytona sandbox. Needs DAYTONA_API_KEY.

Follows the broker of https://www.daytona.io/docs/en/guides/rlm/dspy-rlms: a web server in the sandbox
holds each call until this machine has collected it and posted the result back.
"""

import threading
import time

import httpx
from daytona import Daytona, SessionExecuteRequest

from play_tune import code, play, speakers

# the web server that runs in the sandbox, next to the code
broker = """
import queue, uuid
from flask import Flask, jsonify, request

app = Flask(__name__)
pending, replies = queue.Queue(), {}

@app.post('/call')  # from the code in the sandbox, answers when the result has arrived
def call():
    call_id = str(uuid.uuid4())
    replies[call_id] = queue.Queue()
    pending.put({'id': call_id, **request.json})
    reply = replies[call_id].get()
    del replies[call_id]
    return jsonify(reply)

@app.get('/pending')  # polled from outside the sandbox
def get_pending():
    try:
        return jsonify(pending.get(timeout=2))
    except queue.Empty:
        return jsonify(None)

@app.post('/reply/<call_id>')  # the result, from outside the sandbox
def reply(call_id):
    replies[call_id].put(request.json)
    return jsonify(None)

app.run(port=3000)
"""

# this goes at the top of the code: each call is a request to the broker
stub = """
import json, urllib.request

def call(name, *args):
    body = json.dumps({"call": name, "args": args}).encode()
    request = urllib.request.Request('http://localhost:3000/call', body, {'Content-Type': 'application/json'})
    reply = json.load(urllib.request.urlopen(request))
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"]

def play(note, seconds):
    return call("play", note, seconds)
"""

# the functions the sandbox may call
functions = {'play': play}


def main() -> None:
    daytona = Daytona()
    sandbox = daytona.create()
    try:
        sandbox.fs.upload_file(broker.encode(), '/home/daytona/broker.py')
        sandbox.process.create_session('broker')
        command = SessionExecuteRequest(command='python /home/daytona/broker.py', run_async=True)
        sandbox.process.execute_session_command('broker', command)

        preview = sandbox.get_preview_link(3000)
        client = httpx.Client(base_url=preview.url, headers={'x-daytona-preview-token': preview.token}, timeout=10)
        # wait for the broker to start
        while client.get('/pending').status_code != 200:
            time.sleep(0.2)

        run = threading.Thread(target=sandbox.code_interpreter.run_code, args=(stub + code,))
        run.start()
        with speakers:
            while run.is_alive():
                request = client.get('/pending').json()
                if request is None:
                    continue
                try:
                    reply = {'result': functions[request['call']](*request['args'])}
                except Exception as e:
                    reply = {'error': repr(e)}
                client.post(f'/reply/{request["id"]}', json=reply)
    finally:
        daytona.delete(sandbox)


if __name__ == '__main__':
    main()

"""Daytona: a Flask broker runs in the sandbox, and this machine polls it through the preview URL.

Run with `uv run -m benchmarks.daytona [n] [--save LOCATION]`; see `main` in shared.py.

Design decisions
----------------

A small Flask server runs in the sandbox and holds each call open; the host long-polls it through the
sandbox's preview URL and posts the result back, as in Daytona's DSPy guide
(https://www.daytona.io/docs/en/guides/rlm/dspy-rlms). Each call costs several HTTP requests. The broker
accepts anything that reaches it: the code being sandboxed can post to it on `localhost` and so forge results,
and from outside it is protected only by the preview token. It also needs Flask in the image.

The JSON is the same as on the other providers, so the data and security points in the docstring of shared.py
apply here too; the one about stdout does not, since the calls go over HTTP.
"""

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from daytona import Daytona, SessionExecuteRequest

from .shared import RUN_FEED, Functions, Pool, Session, answer, main

# the web server that runs in a Daytona sandbox: it holds each call until this machine has collected it and
# posted the result back, and passes on the result of each feed
DAYTONA_BROKER = """
import queue, uuid
from flask import Flask, jsonify, request

app = Flask(__name__)
pending, replies = queue.Queue(), {}

@app.get('/ready')
def ready():
    return jsonify(True)

@app.post('/call')  # from the code in the sandbox, answers when the result has arrived
def call():
    call_id = str(uuid.uuid4())
    replies[call_id] = queue.Queue()
    pending.put({'id': call_id, **request.json})
    reply = replies[call_id].get()
    del replies[call_id]
    return jsonify(reply)

@app.post('/done')  # from the code in the sandbox, when a feed has finished
def done():
    pending.put(request.json)
    return jsonify(None)

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

app.run(port=3000, threaded=True)
"""

# run in the sandbox's code interpreter before the first feed
DAYTONA_SETUP = (
    """
import json, urllib.request

def post(path, body):
    request = urllib.request.Request(
        'http://localhost:3000' + path, json.dumps(body).encode(), {'Content-Type': 'application/json'}
    )
    return json.load(urllib.request.urlopen(request))

def call(name, *args):
    reply = post('/call', {'call': name, 'args': args})
    if 'error' in reply:
        raise RuntimeError(reply['error'])
    return reply['result']
"""
    + RUN_FEED
    + """
def feed(code, names):
    try:
        post('/done', {'result': run_feed(code, names)})
    except Exception as e:  # noqa: BLE001
        post('/done', {'error': repr(e)})
"""
)


class DaytonaSession(Session):
    def __init__(self, sandbox: Any, client: Any):
        self.sandbox = sandbox
        self.client = client
        self.setup = DAYTONA_SETUP

    async def feed_run(self, code: str, external_lookup: Functions | None = None) -> Any:
        functions = external_lookup or {}
        source = f'{self.setup}\nfeed({code!r}, {list(functions)!r})'
        self.setup = ''
        # run_code blocks until the feed has finished, so it gets a thread while this one answers its calls
        run = threading.Thread(target=self.sandbox.code_interpreter.run_code, args=(source,))
        run.start()
        try:
            while True:
                message = self.client.get('/pending').json()
                if message is None:
                    if not run.is_alive():
                        raise RuntimeError('the feed ended without a result')
                elif 'call' in message:
                    self.client.post(f'/reply/{message["id"]}', json=answer(message, functions))
                elif 'error' in message:
                    raise RuntimeError(message['error'])
                else:
                    return message['result']
        finally:
            run.join()


class DaytonaPool(Pool):
    def __init__(self) -> None:
        self.daytona = Daytona()

    @asynccontextmanager
    async def checkout(self) -> AsyncIterator[DaytonaSession]:
        sandbox = self.daytona.create()
        try:
            sandbox.fs.upload_file(DAYTONA_BROKER.encode(), '/home/daytona/broker.py')
            sandbox.process.create_session('broker')
            command = SessionExecuteRequest(command='python /home/daytona/broker.py', run_async=True)
            sandbox.process.execute_session_command('broker', command)

            preview = sandbox.get_preview_link(3000)
            headers = {'x-daytona-preview-token': preview.token}
            with httpx.Client(base_url=preview.url, headers=headers, timeout=10) as client:
                # wait for the broker to start
                while client.get('/ready').status_code != 200:
                    await asyncio.sleep(0.05)
                yield DaytonaSession(sandbox, client)
        finally:
            self.daytona.delete(sandbox)


if __name__ == '__main__':
    main('daytona', 'Daytona', DaytonaPool())

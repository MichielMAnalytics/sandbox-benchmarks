"""The four benchmark cases, and the pieces the providers without host function calls share.

Each provider module in this directory has a `Pool`, whose `checkout()` gives a new `Session`. Logfire has
`feed_run` with host functions built in. The others do not, so each runs a small REPL in the sandbox, using the transport
its docs recommend (see the scripts in play_tune/).

This must not import the play_tune scripts: they import `sounddevice`, which fails on a machine with no audio.
"""

import argparse
import asyncio
import json
import statistics
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

Functions = dict[str, Callable[..., Any]]

RESULTS = Path(__file__).parent.parent / 'results'


class Session(ABC):
    """One sandbox, with the interface of a Monty session."""

    @abstractmethod
    async def feed_run(self, code: str, external_lookup: Functions | None = None) -> Any:
        """Run code in the sandbox and return the value of its last expression.

        State is kept between feeds, and the code can call the functions in `external_lookup` on this machine.
        """


class Pool(ABC):
    """What each provider module gives `main`: somewhere to get new sessions from."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    @abstractmethod
    def checkout(self) -> AbstractAsyncContextManager[Session]:
        """A new session, ended on leaving the block. The benchmark times the whole block."""


# seconds between sessions, long enough for a pre-warmed pool to have a warm session ready again
GAP = 1.0
# seconds to wait after a provider refuses a session before trying again
REFUSED_WAIT = 5.0


def get_name() -> str:
    return 'world'


def double(x: int) -> int:
    return x * 2


FIVE_CALLS = 'a = double(1)\nb = double(a)\nc = double(b)\nd = double(c)\ne = double(d)\ne'
EXT = {'external_lookup': {'get_name': get_name, 'double': double}}


async def case_1_plus_1(s: Session) -> None:
    assert await s.feed_run('1 + 1') == 2


async def case_one_call(s: Session) -> None:
    assert await s.feed_run('get_name()', **EXT) == 'world'


async def case_5_feeds(s: Session) -> None:
    for i in range(5):
        assert await s.feed_run(f'x{i} = {i} * 2\nx{i}') == i * 2


async def case_10_feeds_5_calls(s: Session) -> None:
    for _ in range(10):
        assert await s.feed_run(FIVE_CALLS, **EXT) == 32


CASES = [
    ('1 + 1', case_1_plus_1),
    ('one external call', case_one_call),
    ('5 feeds', case_5_feeds),
    ('10 feeds x 5 calls', case_10_feeds_5_calls),
]


async def run(key: str, pool: Pool, n: int) -> dict[str, Any]:
    """Time n sessions of each case, print a line for each and return what `results/<key>.json` holds for them."""
    cases: dict[str, Any] = {}
    for name, case in CASES:
        times: list[float] = []
        refused = 0
        while len(times) < n:
            await asyncio.sleep(GAP)
            start = time.perf_counter()
            try:
                async with pool.checkout() as s:
                    await case(s)
            except Exception as e:
                # Logfire refuses sessions for about 20 seconds after 32 in a row, and boat allows a number of
                # starts a minute; those are not timed
                if 'worker_unavailable' not in str(e) and 'rate_limited' not in str(e):
                    raise
                refused += 1
                await asyncio.sleep(REFUSED_WAIT)
                continue
            times.append((time.perf_counter() - start) * 1000)
        print(
            f'{key:<18} {name:<20} p50 {statistics.median(times):7.0f}  '
            f'min {min(times):7.0f}  max {max(times):7.0f} ms  (n={n})' + (f'  refused {refused}' if refused else ''),
            flush=True,
        )
        cases[name] = {
            'median': round(statistics.median(times)),
            'min': round(min(times)),
            'max': round(max(times)),
            'times': [round(t) for t in times],
        }
        if refused:
            cases[name]['refused'] = refused
    return cases


async def run_pool(key: str, pool: Pool, n: int) -> dict[str, Any]:
    async with pool:
        return await run(key, pool, n)


def main(key: str, provider: str, pool: Pool) -> None:
    """Run the four cases against a pool, each timed from checking out a new session to that session ending.

    `key` names the results file and `provider` is the name shown in the table. With `--save LOCATION` the
    run replaces `results/<key>.json`, keeping the note of the file it replaces.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('n', nargs='?', type=int, default=5, help='sessions per case')
    parser.add_argument('--save', metavar='LOCATION', help='write results/<key>.json; where this was run from')
    args = parser.parse_args()
    cases = asyncio.run(run_pool(key, pool, args.n))
    if args.save:
        path = RESULTS / f'{key}.json'
        result = {
            'provider': provider,
            'date': str(datetime.now(UTC).date()),
            'location': args.save,
            'sessions': args.n,
        }
        if path.exists() and (note := json.loads(path.read_text()).get('note')):
            result['note'] = note
        result['cases'] = cases
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        print(f'wrote {path.relative_to(RESULTS.parent)}')


# runs one feed in the sandbox; `call(name, *args)` is defined by the transport around it
RUN_FEED = """
import ast

state = {}

def run_feed(code, names):
    for name in names:
        state[name] = lambda *args, name=name: call(name, *args)
    tree = ast.parse(code)
    last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
    exec(compile(tree, '<feed>', 'exec'), state)
    if last is not None:
        return eval(compile(ast.Expression(last.value), '<feed>', 'eval'), state)
"""

# the REPL for all but Daytona: feeds arrive on stdin and calls and results leave on stdout, one line of JSON each
STDIO_REPL = (
    """
import json, sys

out = sys.stdout
sys.stdout = sys.stderr  # so that a print() in a feed cannot break the protocol

def send(message):
    out.write(json.dumps(message) + '\\n')
    out.flush()

def call(name, *args):
    send({'call': name, 'args': args})
    reply = json.loads(sys.stdin.readline())
    if 'error' in reply:
        raise RuntimeError(reply['error'])
    return reply['result']
"""
    + RUN_FEED
    + """
for line in sys.stdin:
    feed = json.loads(line)
    try:
        send({'result': run_feed(feed['feed'], feed['names'])})
    except Exception as e:  # noqa: BLE001
        send({'error': repr(e)})
"""
)


def answer(message: dict[str, Any], functions: Functions) -> dict[str, Any]:
    """Run the host function a sandbox asked for."""
    try:
        return {'result': functions[message['call']](*message['args'])}
    except Exception as e:  # noqa: BLE001
        return {'error': repr(e)}


class StdioSession(Session):
    """A session talking to STDIO_REPL; subclasses provide `write(line)` and `readline()`."""

    @abstractmethod
    async def write(self, line: str) -> None: ...

    @abstractmethod
    async def readline(self) -> str: ...

    async def feed_run(self, code: str, external_lookup: Functions | None = None) -> Any:
        functions = external_lookup or {}
        await self.write(json.dumps({'feed': code, 'names': list(functions)}) + '\n')
        while True:
            message = json.loads(await self.readline())
            if 'call' in message:
                await self.write(json.dumps(answer(message, functions)) + '\n')
            elif 'error' in message:
                raise RuntimeError(message['error'])
            else:
                return message['result']

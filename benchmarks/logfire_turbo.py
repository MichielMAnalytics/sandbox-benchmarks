"""Logfire Agent Sandboxes with `pre_warm`, which keeps a buffer of sessions ready to use at checkout.

Run with `uv run -m benchmarks.logfire_turbo [n] [--save LOCATION]`; see `main` in shared.py.

See the docstring of logfire.py for design decisions.

Needs pydantic-monty-client 1.7.
"""

from .logfire import URL, LogfirePool
from .shared import main

if __name__ == '__main__':
    main('logfire_turbo', 'Pydantic Logfire (turbo)', URL, LogfirePool(pre_warm=5))

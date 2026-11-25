# Sandbox Benchmarks

An experiment comparing how code running in a remote sandbox can call functions on the host machine, across
seven sandbox providers: Pydantic Logfire Agent Sandboxes, Modal, E2B, Daytona, Vercel Sandbox, Cloudflare sandboxes
and boat.dev.

Each script in `play_tune/` runs the same program in a sandbox, a tune that calls `play(note, seconds)` 78
times, and the host plays each note through the speakers. The modules in `benchmarks/` time four
cases on each provider.

<!-- results: written by results.py -->

Median milliseconds from GCP us-east4-a, 2026-11-25, from asking for a new session to having the result:

| Provider                                                                       | `1 + 1`    | one external call | 5 feeds    | 10 feeds x 5 calls |
| ------------------------------------------------------------------------------ | ---------- | ----------------- | ---------- | ------------------ |
| [Pydantic Logfire (turbo)](https://pydantic.dev/docs/logfire/agent-sandboxes/) | 26         | 32                | 67         | 618                |
| [Pydantic Logfire](https://pydantic.dev/docs/logfire/agent-sandboxes/)         | 99 (3.8x)  | 107 (3.3x)        | 136 (2.0x) | 847 (1.4x)         |
| [Daytona](https://www.daytona.io)                                              | 133 (5.1x) | 561 (18x)         | 909 (14x)  | 3092 (5.0x)        |
| [Modal](https://modal.com/docs/guide/sandboxes)                                | 346 (13x)  | 471 (15x)         | 457 (6.8x) | 1364 (2.2x)        |
| [E2B](https://e2b.dev)                                                         | 531 (20x)  | 528 (16x)         | 755 (11x)  | 5105 (8.3x)        |
| [Cloudflare sandbox](https://developers.cloudflare.com/sandbox/)               | 848 (33x)  | 692 (22x)         | 785 (12x)  | 1875 (3.0x)        |
| [Vercel](https://vercel.com/docs/sandbox)                                      | 915 (35x)  | 1030 (32x)        | 1253 (19x) | 5316 (8.6x)        |
| [boat.dev](https://boat.dev)                                                   | 1443 (56x) | 2817 (88x)        | 2890 (43x) | 7910 (13x)         |

- Pydantic Logfire (turbo): Pydantic Logfire with `pre_warm=5`: the client keeps five sessions open in the background, so asking for one takes a session that already exists instead of waiting for one to start. They are opened before the timer starts, and the second the benchmark waits between sessions is enough for the pool to refill. Every other row starts its sandbox inside the timed part.
- Daytona: The sandboxes are in Daytona's `us` region.
- boat.dev: Five sessions per case, to stay inside boat.dev's start limits. Its sandboxes are all in the EU.

<!-- /results -->

## Running the cases

You need [uv](https://docs.astral.sh/uv/) and an account with each provider you want to run. Put the keys in a
`.env` file as `export` lines, then install and load them:

```bash
uv sync
. ./.env
```

| Provider                 | Module                          | Needs                                                                                               |
| ------------------------ | ------------------------------- | --------------------------------------------------------------------------------------------------- |
| Pydantic Logfire         | `benchmarks.logfire`            | `LOGFIRE_API_KEY`                                                                                   |
| Pydantic Logfire (turbo) | `benchmarks.logfire_turbo`      | `LOGFIRE_API_KEY`                                                                                   |
| Modal                    | `benchmarks.modal`              | `modal setup` to have been run                                                                      |
| E2B                      | `benchmarks.e2b`                | `E2B_API_KEY`                                                                                       |
| Cloudflare sandbox       | `benchmarks.cloudflare_sandbox` | `CLOUDFLARE_SANDBOX_URL` and `CLOUDFLARE_SANDBOX_KEY`, for your deployment of `cloudflare_sandbox/` |
| Daytona                  | `benchmarks.daytona`            | `DAYTONA_API_KEY`                                                                                   |
| Vercel                   | `benchmarks.vercel`             | `VERCEL_OIDC_TOKEN`, which `vercel env pull` writes and which lasts 12 hours                        |
| boat.dev                 | `benchmarks.boat`               | `BOAT_API_KEY`, and `ssh` on your machine                                                           |

Run a module from the root of the repo, with the number of sessions per case (5 if you leave it out):

```bash
uv run -m benchmarks.modal 15
```

It runs the four cases in turn and prints a line for each. The median, minimum and maximum are milliseconds
from asking for a session to having the result; `end` is the median time ending the session then took:

```
modal              1 + 1                p50     346  min     252  max    1901 ms  end    19 ms  (n=15)
```

Each session creates a sandbox and deletes it afterwards, and the providers bill for them.

Cloudflare has no hosted API for its sandboxes, so that one needs the Worker in `cloudflare_sandbox/` deployed to
your own account first:

```bash
cd cloudflare_sandbox
npm install && npx wrangler deploy    # Docker must be running
npx wrangler secret put API_KEY       # the value you then use as CLOUDFLARE_SANDBOX_KEY
```

`CLOUDFLARE_SANDBOX_URL` is the Worker's address with `wss://` in front.

To run every provider from US east, `gcp_bench.sh` creates a VM in a GCP project of yours, runs them there and
deletes the VM:

```bash
PROJECT=my-project ./gcp_bench.sh 15
```

## How host functions are called

`1 + 1` does not call the host, so it uses each provider's own way of running a program, such as E2B's
`run_code` or `python -c` through Modal's `exec`, and reads what it prints.

The other three cases call functions on the host or keep state between feeds. Only Pydantic Logfire has that
built in. For the others we built a request and reply on whatever the provider's docs show for talking to a
running program, and it is started only for those cases. The docstring at the top of each module in
`benchmarks/`, such as [`benchmarks/modal.py`](benchmarks/modal.py), says why it was done that way and what it
costs; the one in [`benchmarks/shared.py`](benchmarks/shared.py) covers what they have in common.

## Results

Each provider's latest run is a JSON file in `results/`, and `results.py` builds the table above from them. The
figure in brackets is how many times slower that provider is than the fastest at that case.

The times in the table stop when the result arrives. Ending the session, which for most providers means
deleting the sandbox, is timed separately and kept in each file under `end`, since nobody waits for it.

```bash
uv run results.py             # print the table; --ranges for minimum to maximum
uv run results.py --write     # replace the table in this file
```

To update a provider, run its benchmark with `--save` and where you ran it from, then `uv run results.py --write`:

```bash
uv run -m benchmarks.modal 15 --save 'GCP us-east4-a'
```

Times from different places cannot be compared, so the results here are all from a GCP VM in `us-east4`, which
`gcp_bench.sh` does for you: it saves each provider's results and copies them back into `results/`.

[`AGENTS.md`](AGENTS.md) describes the files, how to run them and the credentials each provider needs.

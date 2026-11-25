# Sandbox Benchmarks

An experiment comparing how code running in a remote sandbox can call functions on the host machine, across
seven sandbox providers: Logfire Agent Sandboxes, Modal, E2B, Daytona, Vercel Sandbox, Cloudflare sandboxes
and boat.dev.

Each script in `play_tune/` runs the same program in a sandbox, a tune that calls `play(note, seconds)` 78
times, and the host plays each note through the speakers. The modules in `benchmarks/` time four cases on each provider.

<!-- results: written by results.py -->

Median milliseconds from GCP us-east4-a, 2026-11-24 to 2026-11-25, from checking out a new session to that session ending:

| Provider           | `1 + 1`     | one external call | 5 feeds    | 10 feeds x 5 calls |
| ------------------ | ----------- | ----------------- | ---------- | ------------------ |
| Logfire (turbo)    | 21          | 33                | 64         | 649                |
| Logfire            | 94 (4.5x)   | 107 (3.2x)        | 144 (2.2x) | 738 (1.1x)         |
| Modal              | 398 (19x)   | 494 (15x)         | 482 (7.5x) | 1407 (2.2x)        |
| Daytona            | 582 (28x)   | 592 (18x)         | 959 (15x)  | 3182 (4.9x)        |
| E2B                | 698 (33x)   | 678 (21x)         | 906 (14x)  | 4980 (7.7x)        |
| Cloudflare sandbox | 849 (40x)   | 902 (27x)         | 933 (15x)  | 2668 (4.1x)        |
| Vercel             | 2370 (113x) | 2246 (68x)        | 2434 (38x) | 6203 (9.6x)        |
| boat.dev           | 2524 (120x) | 3005 (91x)        | 2853 (45x) | 7387 (11x)         |

- Logfire (turbo): Logfire with `pre_warm=5`, which keeps a buffer of sessions ready to use at checkout.
- Daytona: The sandboxes are in Daytona's `us` region.
- Cloudflare sandbox: Times leave out deleting the container, which the Worker does after the session ends.
- boat.dev: Five sessions per case, to stay inside boat.dev's start limits. Its sandboxes are all in the EU.

<!-- /results -->

## Running the cases

You need [uv](https://docs.astral.sh/uv/) and an account with each provider you want to run. Put the keys in a
`.env` file as `export` lines, then install and load them:

```bash
uv sync
. ./.env
```

| Provider           | Module                          | Needs                                                                                               |
| ------------------ | ------------------------------- | --------------------------------------------------------------------------------------------------- |
| Logfire            | `benchmarks.logfire`            | `LOGFIRE_API_KEY`                                                                                   |
| Logfire (turbo)    | `benchmarks.logfire_turbo`      | `LOGFIRE_API_KEY`                                                                                   |
| Modal              | `benchmarks.modal`              | `modal setup` to have been run                                                                      |
| E2B                | `benchmarks.e2b`                | `E2B_API_KEY`                                                                                       |
| Cloudflare sandbox | `benchmarks.cloudflare_sandbox` | `CLOUDFLARE_SANDBOX_URL` and `CLOUDFLARE_SANDBOX_KEY`, for your deployment of `cloudflare_sandbox/` |
| Daytona            | `benchmarks.daytona`            | `DAYTONA_API_KEY`                                                                                   |
| Vercel             | `benchmarks.vercel`             | `VERCEL_OIDC_TOKEN`, or `VERCEL_TOKEN`, `VERCEL_TEAM_ID` and `VERCEL_PROJECT_ID`                    |
| boat.dev           | `benchmarks.boat`               | `BOAT_API_KEY`, and `ssh` on your machine                                                           |

Run a module from the root of the repo, with the number of sessions per case (5 if you leave it out):

```bash
uv run -m benchmarks.modal 15
```

It runs the four cases in turn and prints a line for each, with the median, minimum and maximum in milliseconds:

```
modal              1 + 1                p50     398  min     339  max    1915 ms  (n=15)
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

## Results

Each provider's latest run is a JSON file in `results/`, and `results.py` builds the table above from them. The
figure in brackets is how many times slower that provider is than the fastest at that case.

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

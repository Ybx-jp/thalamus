# Getting started

This walks the whole path — clone to a running console — and says what each step
should look like, so you can tell a normal empty state from something that needs
attention.

## 1. Prerequisites

| | Why | Check |
|---|---|---|
| **Docker** | runs the graph | `docker --version` |
| **Python ≥3.11** + [**uv**](https://docs.astral.sh/uv/) | the package and CLI | `uv --version` |
| **jq** | every hook parses its stdin with it | `jq --version` |
| **tmux** | the roster and console drive pinned sessions as tmux windows | `tmux -V` |
| **Claude Code** (`claude`) or **Cursor** (`agent`) | distillation shells out to it | `claude --version` |

`jq` is not optional. The hook layer is shell scripts that parse their stdin with it,
and without it they exit silently rather than loudly.

## 2. Clone and start the graph

```bash
git clone https://github.com/Ybx-jp/thalamus && cd thalamus
docker compose up -d
```

That brings up Gremlin Server on TinkerGraph at `127.0.0.1:8182`. The image is public;
there is no licence file and no account.

The graph lives in the named `thalamus-graph-data` Docker volume, outside the checkout.
`docker compose stop` is safe. `docker compose down -v` deletes your memory.

## 3. Install the package

```bash
uv sync --extra dev
```

This creates `.venv/` with the package and its CLI. The CLI is at `.venv/bin/thalamus`,
which is not on your PATH — prefix commands with `uv run`, or activate the venv:

```bash
uv run thalamus --help          # works from anywhere in the checkout
# or
source .venv/bin/activate       # then plain `thalamus ...`
```

Every command in these docs is written as `thalamus …`; add `uv run` in front if you
have not activated.

## 4. Wire your editor

```bash
uv run thalamus init
```

This installs at **user scope** — `~/.claude/` and `~/.cursor/`, not the checkout — so
the harness arms in every directory you work in, not only here. Because it writes
outside the repo, it lists the full blast radius and asks first.

What it writes:

| Target | What |
|---|---|
| `~/.claude/settings.json` | the hook wirings, by absolute path |
| `~/.claude.json` | the MCP server, registered via `claude mcp add` |
| `~/.cursor/hooks.json`, `~/.cursor/mcp.json` | the Cursor hook suite and the same MCP server |
| `~/.claude/skills/` | symlinks to the shipped skills |
| `~/.claude/agents/` | one derived agent per expert manifest |

Useful flags: `--dry-run` (report, write nothing), `--harness claude` or
`--harness cursor` (one editor only), `--yes` (skip the prompt in a script),
`--uninstall` (remove everything it can prove it installed, leaving your graph,
`~/.thalamus/` and the archive alone).

### Reading the verification output

Install ends by *exercising* what it wired rather than asserting it — it spawns the
real interpreter from a foreign directory, round-trips the Cursor injection spool, and
reads each skill back through its user-scope path.

```
Verification (exercised, not assumed):
  ✓ distillation entry point: `thalamus` resolves from a foreign cwd
  ✓ graph reachable: 0 vertices at ws://localhost:8182/gremlin (fresh — every install starts empty)
  ! cursor distillation CLI: `agent` not on PATH — cursor sessions will retrieve
    and trace but never distill (install it, or extract with `--harness claude`)
```

Three markers:

- **`✓`** — verified by running it, not by checking that a file exists.
- **`!`** — an advisory about your environment, with the command that fixes it. Install
  wires configuration; it does not start your containers or install other vendors'
  binaries. Advisories never fail the install.
- **`✗`** — something the install needs is not in place.

**A graph reporting 0 vertices is a pass.** That is exactly what a fresh install looks
like.

**Running `--check` or `--dry-run` before you have installed will report `✗` on the
things that are not installed yet** — derived agents, user-scope skills, Cursor
wiring. That is the check doing its job on an uninstalled box, not a broken machine.
Run the real `thalamus init` first, then `--check`.

## 5. Relaunch your editor

Hooks and the MCP server arm **per process**. An already-running session picks up
nothing, and `/clear` is not enough — quit and reopen Claude Code or Cursor.

A new session should greet you with a memory prompt naming its scope. Your graph is
empty, so it will have nothing to tell you yet. That is the expected first run.

## 6. Bring up the roster

An expert is a scope declared by a manifest in `config/experts/`. Four ship as
examples: `architect`, `designer`, `eval-methodology`, `literature`.

```bash
thalamus roster            # bring up the tmux roster
thalamus pin literature    # or launch one pinned session directly
thalamus spawn architect   # one on-demand pinned window
```

`thalamus roster` opens tmux windows, one per expert, each running your agent CLI
pinned to that scope. It needs `claude` on your PATH — if the CLI is missing the
window will not survive, so check `claude --version` first.

## 7. Open the console

```bash
thalamus console
```

```
Control plane on http://127.0.0.1:8378  (tmux session `thalamus`)
```

The console is a browser front end over the tmux roster: a tab per window, the live
pane, a composer, the terminal keys a phone keyboard lacks, and one tap to spawn an
expert in a project or restart one so a wiring change arms. It never moves the active
window, so the terminal on your desk stays where you left it.

If you have not started a roster yet, the console tells you so and serves anyway:

```
No windows in tmux session "thalamus".

The console bridges a tmux session — it doesn't create one. Start the roster on the host:

  thalamus roster

Or bridge any tmux session you like:

  tmux new -d -s thalamus -n main
```

The console binds `127.0.0.1` and carries **no authentication**. To reach it from a
phone, put `tailscale serve` in front of that loopback port and publish it on your
tailnet — which is also what makes it installable as a PWA. Do not bind it to a public
interface.

## 8. Seed memory from transcripts you already have

If you have been using Claude Code, every session is already on disk as JSONL, and you
can derive memory from it:

```bash
thalamus bootstrap                  # list what's available
thalamus bootstrap -- <project>     # dry run: retain + extract
thalamus bootstrap -- <project> --write
thalamus extract                    # stage 2: claims and threads, via a model
```

Bootstrapping runs in two stages. Stage 1 is deterministic and free — sessions,
sources, artifacts, and the file-touch edges anchored to the exact messages that
touched each file, recovered from tool-call records. Stage 2 needs judgement, so it
goes through a headless model pass to produce claims and open threads.

> **Transcripts contain whatever was on screen, credentials included.** The archive
> lives at `~/.thalamus/archive/`, outside the repo — not merely gitignored.
> `bootstrap` scans for secrets and **reports**; it never redacts, because evidence
> that has been quietly rewritten is not evidence. Read what it reports before you
> share a graph with anyone.

## 9. Look at what it remembers

```bash
thalamus visualize          # browser graph explorer over the live graph
thalamus pulse              # live telemetry over the eval loop
thalamus contract check     # audit the graph against the contract
```

From inside an agent session, the MCP tools are the retrieval surface —
`memory_open_threads` is the entrypoint. See [concepts](concepts.md) for what the
scopes and tiers mean, and the [CLI reference](cli.md) for everything else.

## Where things live

| | |
|---|---|
| The graph | Docker volume `thalamus-graph-data` |
| Retained transcripts | `~/.thalamus/archive/` |
| Ledgers, pins, eval state | `~/.thalamus/` |
| Expert manifests | `config/experts/` in the checkout, or `$THALAMUS_CONFIG_DIR/experts/` |

Both the graph and the archive sit outside the checkout by construction. There is
nothing in the tree to ship.

TinkerGraph holds the graph in memory and writes back on clean shutdown, so every
write path flushes when it finishes and `thalamus snapshot` does it on demand.
`docker compose stop` is safe; `docker kill` costs you whatever was written since the
last flush.

## Troubleshooting

**`thalamus: command not found`** — the CLI is in `.venv/bin`. Use `uv run thalamus`
or activate the venv.

**`Cannot connect to host localhost:8182`** — the graph container is not running.
`docker compose up -d`.

**A new session doesn't mention memory** — hooks arm per process. Fully quit and
reopen your editor.

**`thalamus roster` succeeds but the console shows no windows** — the roster window
started and exited, usually because `claude` is not on PATH. Check `claude --version`.

**Port 8378 already in use** — something else has the console port. Stop it, or pass a
different port.

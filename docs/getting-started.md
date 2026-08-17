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
and without it they exit silently rather than loudly. If it goes missing *after*
install, the SessionEnd hook writes what happened to
`~/.thalamus/logs/hook-failures.log` and `thalamus init --check` reads it back.

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
  ○ derived agents installed: none written yet to ~/.claude/agents — `thalamus init` writes one per expert manifest
  ! cursor distillation CLI: `agent` not on PATH — cursor sessions will retrieve
    and trace but never distill (install it, or extract with `--harness claude`)
```

Four markers:

- **`✓`** — verified by running it, not by checking that a file exists.
- **`○`** — not installed yet, with the command that installs it. This is what a box
  that has never run `thalamus init` looks like, and it never fails the run.
- **`!`** — an advisory about your environment, with the command that fixes it. Install
  wires configuration; it does not start your containers or install other vendors'
  binaries. Advisories never fail the install.
- **`✗`** — something the install needs is in place and wrong: a skill link that
  dangles, a hooks file holding only some of the wirings, an MCP entry that no longer
  matches this checkout. Only these fail the run.

**A graph reporting 0 vertices is a pass.** That is exactly what a fresh install looks
like.

**`--check` and `--dry-run` are safe to run before you have installed.** Everything
not written yet — derived agents, user-scope skills, Cursor wiring — comes back `○`
with the command that writes it, and the run exits 0. `--dry-run` always ends by
saying it wrote nothing, including on a run that found faults.

## 5. Relaunch your editor

Hooks and the MCP server arm **per process**. An already-running session picks up
nothing, and `/clear` is not enough — quit and reopen Claude Code or Cursor.

A new session should greet you with a memory prompt naming its scope. Your graph is
empty, so it will have nothing to tell you yet. That is the expected first run.

## 6. Bring up the roster

An expert is a scope declared by a manifest in `config/experts/`. Five ship as
examples: `architect`, `designer`, `eval-methodology`, `literature` and `qe`. Two of
them are worth reading before you write your own — `designer` shows how a scope is
given its own MCP tools, and `qe` shows a scope defined by what it must *not* produce.

To use your own roster instead, point `THALAMUS_CONFIG_DIR` at a directory holding an
`experts/` subdirectory. The same variable supplies the eval task battery from
`tasks/`.

```bash
thalamus roster            # bring up the tmux roster
thalamus pin literature    # or launch one pinned session directly
thalamus spawn architect   # one on-demand pinned window
```

`thalamus roster` opens the `main` anchor window in a tmux session; experts are
spawned on demand from there or from the console, and `--all` opens one window per
manifest. Each window runs your agent CLI pinned to that scope, so it needs `claude`
on your PATH. A window whose command exits before it can be called started is
reported as a failure with what the pane printed, and the command exits non-zero.

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

**`nothing listening on localhost:8182 — start it with docker compose up -d`** — the
graph container is not running. Every surface says this the same way, whether you hit
it from `thalamus init --check`, a CLI command, or a recall tool inside a
session.

**A new session doesn't mention memory** — hooks arm per process. Fully quit and
reopen your editor.

**Memory stopped accumulating and nothing said so** — a hook needs `jq`, and
SessionEnd also needs `uv`. If either leaves your PATH after install, the hook cannot
run at all; it records the loss in `~/.thalamus/logs/hook-failures.log` and
`thalamus init --check` reports how many sessions ended undistilled and when the last
one was. Restore the binary, then re-run the check. Sessions that ended in the gap
can still be recovered with `thalamus bootstrap` and `thalamus extract`.

**`Roster failed: … did not start`** — a roster window was created and its command
exited before it could be called started. The message quotes what the pane printed,
which is the diagnosis when there is one; when the command could not be executed at
all there is nothing to quote, and the cause is almost always that `claude` is not on
PATH. Check `claude --version`. With `--all`, the scopes that did come up are left
running — only the dead ones are named, and the exit code is non-zero either way.

**`port 8378 is already in use`** — usually a `thalamus console` you still have
running. Stop it, or serve this one elsewhere with `thalamus console --port <n>`.

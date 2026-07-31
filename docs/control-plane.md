# The control plane

**Drive your pinned sessions from your phone.**

A pinned session is an OS process in a tmux window ([07](07-harness-integration.md),
"the process is the pin"), which makes tmux the one place all of them are
addressable at once. `thalamus console` puts a small HTTP server in front of that
tmux session and serves a browser client over it: one tab per window, the live
pane, a composer, the terminal keys a phone keyboard doesn't have, and buttons for
the two operations that otherwise need a laptop — spawning an expert session in a
project, and restarting one so a wiring change arms.

It reads panes with `tmux capture-pane` and sends input with `tmux send-keys`,
always addressing windows *by index*, so the session's active window never moves
and a terminal attached to the same session is left exactly where you put it. You
can drive the roster from a phone while your desk is still logged into it.

Installable to a home screen as a PWA, and it works in any browser without that.

---

## Quick start

Assumes the [main quick start](../README.md#quick-start) is done — Thalamus
installed, `thalamus` on PATH. Beyond that you need **tmux** and the **claude**
CLI, which the roster launches.

```bash
thalamus roster        # opens tmux session `thalamus` with the `main` anchor window
thalamus console       # serves http://127.0.0.1:8378
```

Open <http://127.0.0.1:8378> and you have it. Ctrl+C stops the server; the tmux
session and every session in it keep running — the console is a window onto the
roster, never its owner.

Nothing else is required. The rest of this document is reaching it from a phone,
keeping it running, and what the buttons do.

### If you only ever use one machine

`thalamus console` in a spare terminal, or backgrounded, is a complete setup. Skip
to [Using it](#using-it).

---

## Reaching it from your phone

**The console has no authentication and does not pretend to.** It binds
`127.0.0.1` by default, and anything that can reach it can type into your agent
sessions with your shell's privileges. So the whole question is which existing
authenticated path you put in front of it. Three that work, in the order most
people should try them:

### 1. An overlay network (simplest)

[Tailscale](https://tailscale.com) or equivalent gives every device an identity
and a private address; the console then only has to be reachable on that network.

```bash
tailscale serve --bg --set-path /plane http://127.0.0.1:8378
```

That publishes it at `https://<your-machine>.<tailnet>.ts.net/plane/` over HTTPS,
reachable from your phone anywhere, and not reachable from the internet. Keep the
console bound to loopback — `serve` connects to it locally.

HTTPS matters beyond eavesdropping: browsers only install a PWA and only register
a service worker on a secure origin, so "add to home screen" needs it.

### 2. An SSH tunnel (nothing to install on the server)

```bash
ssh -N -L 8378:127.0.0.1:8378 you@your-machine
```

Then open `http://127.0.0.1:8378` on the client. Fine on a laptop; awkward on a
phone, and no PWA install (plain `http://` on a non-loopback origin isn't secure).

### 3. A reverse proxy that authenticates

Caddy, nginx, or anything with real auth in front, terminating TLS. The client is
written for this: **every URL it requests is relative**, so it works under any
mount path as long as the proxy strips the prefix before forwarding. A Caddy
example:

```caddyfile
your.domain {
  basic_auth { you $2a$14$... }          # or forward_auth to your IdP
  handle_path /plane/* {
    reverse_proxy 127.0.0.1:8378
  }
}
```

`handle_path` (not `handle`) is the prefix-stripping form. Reached without the
trailing slash, the page redirects to add it before any resource loads.

### What not to do

`thalamus console --host 0.0.0.0` on a network you don't control publishes an
unauthenticated remote shell. The flag exists because a host binding is sometimes
genuinely needed behind a proxy on another interface, and the server prints a
warning when you use it.

---

## Using it

**Tabs** are windows. The dot pulses when a session's screen changed since the
last poll, so you can see which one is talking while you read another.

**The workspace bar** appears only once your sessions span more than one
directory, and filters the tabs to one project. A filtered-away session that
changes lights up its workspace chip, so filtering never makes you blind to the
others.

**The composer** sends a line to the active session. `/` at the start opens the
slash-command strip — the claude built-ins plus your user skills plus *that
window's project* skills, since windows sit in different directories. The keycap
row has what a phone keyboard lacks: `esc`, `mode` (Shift+Tab, the permission-mode
cycle), arrows, page up/down, `tab`, `⏎`, `clr` (Ctrl-U) and `⌃C`. `A−`/`A+` nudge
the font off the auto-fit size, which is computed so a full pane line fits your
screen without horizontal scrolling.

**＋ spawns a session**: pick an expert scope and a directory, and the server opens
a detached pinned window there. The scope decides which memory it reads and writes;
the directory decides what the work is about. See
[02](02-expert-subgraphs.md) for what that pairing means.

**⚙ is the admin sheet**:

- **restart** replaces a window's claude process. MCP servers and hooks arm *per
  process* (lab/001), so this is how a wiring change actually takes effect. It
  sends `/exit` — which fires SessionEnd, so the session distills to memory
  normally — waits up to 4 minutes for it, then respawns the window with its
  original command and `THALAMUS_SCOPE` intact. Only a session that hangs past the
  budget gets force-killed, and that one skips distillation.
- **close** ends a session the same graceful way and removes its window. The
  anchor (the lowest-indexed window) can't be closed: it's the console's reference
  directory and the last thing keeping the roster non-empty.
- **roster sync** re-runs `thalamus roster`, which is idempotent — it recreates
  the anchor if it exited and leaves everything else alone.
- **Services** is hidden unless you named units with `--service` (below).

Restarting or closing the session you're *reading* ends that conversation, so the
prompt for the viewed window is worded more sharply than the others.

### On a desktop browser

At a fine pointer and ≥900px the client switches engines: keystrokes go straight
to the pane as you type (`keys: direct`, toggleable), paste goes through, and the
poll speeds up while you're typing. `full` is fullscreen. The phone surface is
deliberately untouched by all of it — it's the one whose failure mode is
relaunching an app from a home screen.

### Install it to your home screen

On a secure origin, Chrome offers an install prompt and the app gets its own icon,
no browser chrome, and an offline shell. iOS Safari never offers the prompt: use
Share → *Add to Home Screen*. The service worker caches the shell network-first,
so the app is always the latest version when the server is reachable, and shows
the cached shell rather than a browser error page when it isn't. API calls are
never cached — a stale pane would be a lie.

---

## Keeping it running

A user unit, so it starts with your session and restarts if it dies:

```ini
# ~/.config/systemd/user/thalamus-console.service
[Unit]
Description=Thalamus control plane
After=default.target

[Service]
Type=simple
WorkingDirectory=%h/code/thalamus
ExecStart=%h/code/thalamus/.venv/bin/thalamus console --service thalamus-console.service
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now thalamus-console
loginctl enable-linger $USER     # so it survives logout / starts at boot
```

**It is a *user* unit.** Without `--user`, `systemctl is-active` reports
`inactive` while the console is plainly serving, and `restart` hangs asking for a
root password it will never get.

`--service thalamus-console.service` is what puts a unit in the admin sheet's
Services section. Listing the console's own unit there is the point: restarting it
goes through `systemd-run`, so the transient unit escapes the console's own cgroup
and the restart survives killing the process that requested it. Name any other
units you want reachable from your phone the same way (`--service` repeats).

The tmux session is separate and outlives the console. If you want it up at boot
too, a second unit running `tmux new -A -s thalamus` gives you one to attach to
from a terminal.

---

## Configuration

Everything that differs between machines is a flag. There is no config file, and
nothing about one operator's setup is baked into the code.

| Flag | Default | What it does |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. Off-loopback prints a warning — there's no auth here |
| `--port` | `8378` | Port |
| `--session` | `thalamus` | tmux session to drive |
| `--project-root` | this checkout | Where roster sync runs |
| `--dir PATH` | the project root | Star a directory in the spawn picker (repeatable) |
| `--scan ROOT` | the project root's parent | Offer every git repo one level under ROOT (repeatable) |
| `--service UNIT` | none | A systemd `--user` unit the admin sheet may restart (repeatable) |

The spawn picker's directory list is also the **whitelist**: a spawn request is
checked against the same computation that built the list, so the client can only
ever open a session somewhere it was offered.

---

## How it works

`src/thalamus/console/` — `server.py` plus `static/`. Around 550 lines of stdlib
Python and a dependency-free client.

- **Stdlib `http.server`, not FastAPI** like `pulse/` and `plane/`. One of its jobs
  is restarting the systemd unit hosting it; the fewer moving parts between a tap
  on a phone and a tmux call, the better.
- **Every tmux call is an argv list, never a shell string.** Pane text and typed
  input are data. Nothing captured from a pane and nothing typed into the composer
  can become a command.
- **Windows are addressed by index, never by name.** Names aren't unique once the
  same expert is spawned in two directories, and switching the active window would
  yank an attached terminal somewhere the person at the keyboard didn't ask to go.
- **Keys are an allowlist.** The client names a key (`ctrl-c`, `shift-tab`); the
  server maps it. A request can never hand tmux an argument.
- **Spawning and roster sync call `harness/pin.py` directly** rather than shelling
  out to the CLI, so the window mechanics — derived agent write, detached create,
  window-size pin — have exactly one implementation.
- **The client polls.** 1.2s on a phone, 100ms while typing on a desktop. A tight
  loop in the UI is not a slow page: it starves the event loop, Android kills the
  renderer, and the operator has to relaunch the app from the home screen. The poll
  is a self-scheduling chain armed from one completion callback, never a promise
  chained back into its own caller.

## Troubleshooting

**"connecting" forever.** The server is unreachable — check `curl
127.0.0.1:8378/api/panes` on the host, and `systemctl --user status
thalamus-console` if you unitized it.

**No tabs, or "No output captured".** There's no tmux session by that name yet, or
it has no windows. `thalamus roster` creates it; the console prints a warning at
startup when it can't find one, and serves anyway so the ＋ button still works.

**A restart never finishes.** The session is holding a dialog `/exit` can't
dismiss. It force-respawns after 4 minutes; that path skips distillation.

**Slash commands are missing.** They're read per-window from `~/.claude/skills`
and that window's `.claude/skills`, fresh on each tab switch.

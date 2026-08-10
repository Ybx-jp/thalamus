# The console

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

**The workspace bar** appears once your sessions span more than one directory, or
any of them is in a room, and filters the tabs to one project (and/or one room). A
filtered-away session that changes lights up its workspace chip, so filtering never
makes you blind to the others.

**The composer** sends a line to the active session. `/` at the start opens the
slash-command strip — the claude built-ins plus your user skills plus *that
window's project* skills, since windows sit in different directories. The keycap
row has what a phone keyboard lacks: `esc`, `mode` (Shift+Tab, the permission-mode
cycle), arrows, page up/down, `tab`, `⏎`, `clr` (Ctrl-U) and `⌃C`. `A−`/`A+` nudge
the font off the auto-fit size, which is computed so a full pane line fits your
screen without horizontal scrolling.

**`read` switches to the transcript view.** The pane view mirrors a *rendering* of
the session: an 80-column repaint, colours stripped by tmux, reflowing under you
while a turn streams. The read view shows the session itself — Claude Code writes
every turn to a JSONL transcript, and the server projects that into flowing prose
with each tool call collapsed to one tappable line, so a forty-line diff reads as
`Edit docs/09-schema-and-federation.md`. Tap a line for its output; tap `term` to
go back. Text wraps to your screen instead of to the session's columns, and since
the transcript is written a turn at a time rather than a token at a time, text
lands as finished blocks instead of shifting mid-sentence.

Prose is rendered as the markdown it was written in: fenced code, inline code,
headings, lists, quotes, rules, emphasis, and links. The split that matters on a
phone is that **prose reflows and code does not** — a code block holds its lines
and scrolls on its own axis, because a wrapped shell command is a misread shell
command, and the page itself never scrolls sideways. Pipe tables are left as
literal text: a table narrower than its columns is less readable than the source.
Rendering escapes first and injects only its own tags, and link targets are held
to http(s) and site-relative — transcript text is whatever a tool printed, not
something the operator wrote.

It is a second view, not a replacement, for one specific reason: **a pending
permission prompt is never written to the transcript.** Nothing is recorded while
the dialog is on screen, so a tool call with no result is either still running or
blocked waiting on you, and the feed cannot tell which. When a call stays open the
read view says so and points at the terminal, which can. Approve things in `term`.

The view needs to know which session is in a window, which it reads from the pin
ledger by tmux pane id. Sessions started before the console recorded that resolve
by a narrower fallback — process start time joined on scope and directory — which
**refuses when two windows share a scope and a directory**, since showing the wrong
session's transcript is worse than showing none. Restart the window (⚙ → restart)
and it resolves exactly from then on.

**＋ spawns a session**: pick an expert scope, a directory, and a room, and the
server opens a detached pinned window there. The scope decides which memory it
reads and writes; the directory decides what the work is about. See
[02](02-expert-subgraphs.md) for what that pairing means.

The same sheet reports **distillation**, because ending a session and distilling it
are not the same event. `/exit` fires SessionEnd, which launches `thalamus extract`
*detached* and lets the window go; the memory is written minutes later by a process
with no window, no tab and no other place to report itself. A row appears per
session still distilling and per session that finished badly:

- **distilling** — a pulsing dot and the elapsed time. Typical is two to four
  minutes.
- **an error** — red, with the reason from the extract log, and it stays until you
  tap ✕. This is the case worth having: a failed extraction exits *zero*, so
  nothing else on the box would ever mention that a conversation was not recorded.
  A distillation that stops being written to for twenty minutes counts as failed —
  the process died rather than ran long.

A clean finish removes its own row, so **an empty section means nothing is owed**,
and the ＋ carries a dot when the sheet has something in it. Only sessions in the
pin ledger are counted: subagents fire SessionEnd too and always fail (they have no
transcript of their own), but they never write a ledger entry, which is what
separates them from real sessions. Dismissals live in
`~/.thalamus/console/distill-dismissed.json`, counted in distillation runs rather
than stamped in time, so a session that distills again later and fails again comes
back — while the `thalamus eval sync` output the hook appends a few seconds behind
extract does not bounce a row you just dismissed.

**Rooms** are the third choice on that sheet, and default to `solo`. A room is a
private roster: its members can see and message each other and nobody else, which
is a boundary in the harness itself rather than a convention
([07](07-harness-integration.md)). Tapping `+ new` and naming one is all it takes
to create it — the launcher provisions the room the first time a member enters, so
there is no setup step that needs a keyboard.

A room member's tab takes its colour from the **room** rather than its scope, so
co-membership is what reads at a glance: two `homelab` sessions in different rooms
are different colours, and a room's `main` and `literature` are the same one. A ◈
marks the tab, since six palette entries cannot promise two rooms different
colours, and the workspace bar grows a room row — a second filter that composes
with the directory one, because "what project" and "which collaboration" are
different questions about the same window.

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

With `--frames`, the desktop surface can also render the pane inside a panel drawn
in a background image — `frame` toggles (F12), `▸` cycles (F9). Off by default and
no artwork ships with it; see [frame-themes.md](frame-themes.md).

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
Description=Thalamus console — tmux bridge for the pinned roster
After=default.target

[Service]
Type=simple
WorkingDirectory=%h/code/thalamus
# PATH must be pinned, not inherited — see "Pin PATH in the unit" below.
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
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

### Pin PATH in the unit

A tmux pane inherits the PATH of the *client that created the window* — which, for
a spawn from your phone, is the console process. A systemd user unit gets no
login-shell PATH, and **at boot** the user manager's PATH has no `~/.local/bin`,
which is where `claude` and `uv` live. A desktop login later adds it via
`import-environment`, so the box looks fine until it reboots unattended.

The failure is silent in every layer: `tmux new-window` returns 0 as soon as it has
forked, so a command that cannot exec leaves a window that dies instantly and is
reaped while tmux, `pin`, and the console all report success. It presents as
"spawning is broken" — and worse, the roster's anchor dies the same way, and with
no windows left the tmux server exits, taking the whole roster with it.

Hence `Environment=PATH=` in the unit, and hence the console confirms a spawned
window is still alive before reporting success. Never trust an exit code alone
here.

`--service thalamus-console.service` is what puts a unit in the admin sheet's
Services section. Listing the console's own unit there is the point: restarting it
goes through `systemd-run`, so the transient unit escapes the console's own cgroup
and the restart survives killing the process that requested it. Name any other
units you want reachable from your phone the same way (`--service` repeats).

The tmux session is separate and outlives the console. If you want it up at boot
too, give it its own unit — and let **`thalamus roster`** be what creates it:

```ini
# ~/.config/systemd/user/thalamus-roster.service
[Unit]
Description=Thalamus roster
After=network.target
Before=thalamus-console.service        # and any unit that attaches a terminal

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=%h/code/thalamus
ExecStart=%h/code/thalamus/.venv/bin/thalamus roster
KillMode=process
```

**Whichever unit creates the session defines window 0**, and the lowest-indexed
window is the anchor — un-closable, and the reference directory for roster sync.
A unit running bare `tmux new -A -s thalamus` (or a web terminal doing it on
first connect) puts a *shell* there, and it then outranks every real session for
the life of the tmux server: roster sync adds `main` beside it rather than
reclaiming index 0, and **restart** on it types `/exit` into a shell, so the
recycle hangs its whole 4-minute grace. Ordering the roster first is what keeps
the anchor a real session.

`KillMode=process` matters for the same reason: the tmux server is forked by
`ExecStart` and stays in the unit's cgroup, so the default `control-group` would
take every session down with a `systemctl --user restart` of this unit.

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
| `--frames PATH` | none | Frame-theme definitions for the desktop client ([frame-themes.md](frame-themes.md)) |

The spawn picker's directory list is also the **whitelist**: a spawn request is
checked against the same computation that built the list, so the client can only
ever open a session somewhere it was offered.

### Running it without a checkout

The tmux bridge is stdlib-only and the expert layer is imported on use, so the
console runs under a bare `python3` with nothing else installed:

```bash
tmux new -d -s thalamus -n main
python3 -m thalamus.console.server      # or: python3 src/thalamus/console/server.py
```

You get panes, input, keys, the composer and the whole client. What you don't get
is the expert layer — the scope list is empty, and spawn, roster sync and rooms
report themselves unavailable rather than failing to import. Nothing else changes.

This is not a supported-configuration matrix so much as a design constraint: one of
this server's jobs is restarting the unit that hosts it, so the fewer moving parts
between a tap and a tmux call, the better. Keeping the bare path working is what
keeps that true.

---

## How it works

`src/thalamus/console/` — `server.py`, `transcript.py` and `distill.py` plus
`static/`. Stdlib Python and a dependency-free client.

- **Stdlib `http.server`, not FastAPI** like `pulse/` and `plane/`. One of its jobs
  is restarting the systemd unit hosting it; the fewer moving parts between a tap
  on a phone and a tmux call, the better.
- **The read view is a deferred import.** It reuses the harness's transcript
  parsing, so `transcript.py` is imported on use like the expert layer — a console
  running under a bare `python3` keeps the pane mirror and reports the read view
  unavailable rather than failing to start.
- **The transcript is read forward from a byte offset, never re-parsed.** Claude
  Code's JSONL is append-only: prefix bytes never change, the inode is stable, and
  mutable state (`mode`, `relocated`) is re-appended under last-wins semantics
  rather than rewritten. Tool result bodies stay on the server and are fetched only
  when a reader expands one — a real session's 276 items serialise to 278KB
  otherwise, against 30KB with the bodies split off.
- **Windows join to sessions by tmux pane id**, recorded in the pin ledger by the
  SessionStart hook. A window *index* renumbers when a window closes, and name,
  scope and directory are all routinely shared by two windows at once; the pane id
  is unique per window, stable for its life, and survives the respawn a recycle
  performs.
- **Distillation state is derived, not tracked.** The SessionEnd hook forks and
  exits, so there is no lockfile, pid file or status record to read — the whole
  state machine is `~/.thalamus/logs/session-end-<sid8>.log`, joined against the
  pin ledger to drop subagent residue (two thirds of the logs on a working box).
  It rides the poll the client already runs rather than getting a loop of its own,
  and is cached against (mtime, size) so a steady-state poll opens no file.
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

### When it lies to you

Every layer here reports success early, so the useful question is rarely "did it
fail" but "which layer is answering".

**A spawn reports success and no window appears.** The console now catches this by
diffing the window list around the spawn, but to see it directly, make dead windows
stay put and read the pane:

```bash
tmux set -wg remain-on-exit on     # -wg: a session-level set is NOT inherited by new windows
```

Spawn again, then `tmux list-windows -a -F '#{window_index} #{pane_dead} #{pane_start_command}'`.
A window with `pane_dead 1` never execed its command — almost always PATH.

**The phone disagrees with the server.** Rule the layers out in this order, because
each one masks the next:

1. `curl 127.0.0.1:8378/api/panes` on the host — if this is wrong, nothing else
   matters and the problem is tmux or the console.
2. Load the page in a desktop browser on the same network. If desktop is right and
   the phone is wrong, it is the client, not the server.
3. In the phone's browser, unregister the service worker and hard-reload. The shell
   is network-first, so a stale SW is rare but not impossible.
4. If the phone is a home-screen install, suspect **WebAPK scope**. Android installs
   ignore ports and match on path prefix, so two apps published under overlapping
   paths on one host collide, and the icon can silently open the other one. Keep
   each app's mount path disjoint.

**A restart of the console kills the console.** Restart it through `systemd-run`,
not `systemctl restart` from inside itself — the transient unit escapes the
console's own cgroup, which is exactly what the admin sheet's Services button does.

**tmux 3.4 segfaults on startup.** `window-size manual` set *globally* does it.
`pin` sets it per-window for this reason.

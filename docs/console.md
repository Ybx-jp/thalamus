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
tailscale serve --bg --set-path /console http://127.0.0.1:8378
```

That publishes it at `https://<your-machine>.<tailnet>.ts.net/console/` over HTTPS,
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
  handle_path /console/* {
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

**`say` reads the active window aloud, from wherever you left off.** It speaks on
a tap and never on its own: nothing is narrated unattended, and only the window
you have selected can talk, so a roster of five sessions can never talk over
itself. Tap again to stop. The control sits in the always-visible key row rather
than inside the read view, because the read view is opt-in per device — a control
behind a toggle a device never enabled is a control that device does not have.

**It appears only on a console started with `--voice URL`.** The service is a
separate unit with a model download behind it (below), so a console that assumed
one would hand every operator a button whose only behaviour is to fail — and the
reason lands in the server's stderr, which is not where the person holding the
phone is looking. The client asks `/api/voice` before it draws anything; without a
service both `/api/say` and `/api/say/ack` are 404 and the button is absent rather
than dead. `$THALAMUS_VOICE_URL` supplies the flag's default, so a box already
running the unit keeps its setting.

Each session keeps a listening position:

- **Tap** speaks what you have not heard yet. The first tap on a session falls
  back to its latest turn rather than the whole history.
- **The position moves when playback ends,** not when the audio is made. Stopping
  halfway means the next tap resumes where your ears stopped, not where the
  synthesiser got to.
- **Caught up** greys the control and stays silent — that is the ordinary resting
  state of a session you follow, not a failure worth announcing.
- **Long-press** re-reads the current turn from its start, for when you missed it
  rather than when you want what came next.
- **Tap any paragraph in the read view** to start listening there; everything
  above it counts as heard, since you just read it to find the place. The chosen
  block keeps a coloured left edge.

The start point travels in the audio request rather than a call that precedes it.
Marking and *then* playing is the natural shape and puts `play()` after an await,
which spends the user activation a phone requires — the same reason the plain tap
assigns `src` and plays in one gesture. Positions are process-local and are not
persisted: where you are in listening to a session is a fact about the last few
minutes, and a console restart is a fine time to forget it.

What you hear is not the reply read out. It is rewritten for the ear: fenced code
is dropped, `src/thalamus/console/server.py` becomes "console server", identifiers
are split into words, acronyms are spelled, and a commit hash goes character by
character. Numbers, versions, hashes, identifiers and acronyms are extracted from
the raw turn *before* the rewrite and checked against the finished utterance; if
one went missing, the console speaks a short notice instead of the update. A
listener told nothing knows to go and look, while a fluent sentence with the wrong
number in it is undetectable and cannot be rewound. Long turns are cut at a
sentence at roughly ninety seconds and say so, rather than reading for five
minutes. The transform is `console/speech.py`; the budget is
`DEFAULT_BUDGET_CHARS`.

Speech needs `thalamus-voice.service` (below), named with `--voice`. A console
started without it simply has no `say` control; one whose service dies turns the
control red and is otherwise unaffected.

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
headings, lists, quotes, rules, emphasis, links, and pipe tables. The split that
matters on a phone is that **prose reflows and code does not** — a code block holds
its lines and scrolls on its own axis, because a wrapped shell command is a misread
shell command, and the page itself never scrolls sideways. A table holds its columns
for the same reason and scrolls the same way: the column a cell sits in is what the
cell says, so reflowing a five-column table to 390px would keep every character and
lose the arrangement that carried the meaning. A table is claimed only on a header
row plus a delimiter row of matching width beneath it, which is why a lone `---`
under a sentence is still a rule.
Rendering escapes first and injects only its own tags, and link targets are held
to http(s) and site-relative — transcript text is whatever a tool printed, not
something the operator wrote.

**A question put to you renders open, not collapsed.** `AskUserQuestion` is the
one tool call the reader must act on rather than watch, and unlike a permission
prompt it *is* written to the transcript the moment it is asked — question,
options, and all. So the read view shows it in full for as long as the session
sits blocked, marked as waiting on you, instead of collapsing it to a chip that
looks like a slow tool. Answer it in `term` with the ↑ ↓ keycaps and `⏎`: the
dialog is a modal, and typing into the composer would discard the text and
actuate whichever option happened to be highlighted (hazard 9).

The waiting state reads the newest item on the *main* thread rather than the
newest item outright, because a subagent writes into the same transcript — its
traffic would otherwise look like progress while the session is stopped.

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

A read view showing one short exchange that never advances is a third state, and it
is not a stall: the window's pane id was claimed by a headless `claude -p` spawned
inside it, which inherits `TMUX_PANE` like any child process
([console-hazards.md](console-hazards.md) §10). The next SessionStart in that window
takes the key back.

A window that has been identified but has written nothing is a different state,
and the view says so plainly rather than reporting the refusal above: Claude Code
creates the transcript on the first turn, so a freshly spawned window has none
until someone types into it. Send it a message and the feed starts.

**＋ spawns a session**: pick an expert scope, a harness, a directory, and a room,
and the server opens a detached pinned window there. The scope decides which memory
it reads and writes; the directory decides what the work is about. See
[02](02-expert-subgraphs.md) for what that pairing means.

**The harness row is `LAUNCH_SHAPES`**, sent by `/api/spawn-options` rather than held
by the client, because that table is also what a spawn request is validated against —
a chip the phone invented would be refused after the tap. Each entry carries whether
that harness's pin has a persona, and the sheet prints the caveat when it does not:
a Cursor window routes its memory and holds its boundary but never reads the expert's
charter, which is a different object from a Claude Code pin ([07](07-harness-integration.md))
and is invisible once the window exists. A request that names no harness gets Claude
Code — the endpoint is driven by hand over the tailnet too.

**Distillation is a state of a session, not a list of its own**, and it is drawn on
that session's roster row. Ending a session and distilling it are not the same
event: `/exit` fires SessionEnd, which launches `thalamus extract` *detached* and
lets the window go, so the memory is written minutes later by a process with no
window and no other place to report itself. The record routinely outlives its
window, and a row then renders from the record alone.

- **distilling** — the elapsed time in the state slot. Typical is two to four
  minutes.
- **stalled** — past twenty minutes with nothing written. It keeps the ordinary row
  geometry because the process may still finish.
- **abandoned** — past an hour, three times the stall clock. It cannot still be
  running, so the row takes the terminal band.
- **failed** — the band, with the reason from the extract log verbatim. This is the
  case worth having: a failed extraction exits *zero*, so nothing else on the box
  would ever mention that a conversation was not recorded.
- **never distilled** — the band, for a window killed before SessionEnd could run.

A clean finish is served as no record at all, so **success is drawn as nothing** and
the absence is unambiguous once every other outcome draws something. A banded row
stays until dismissed: if it vanished on the next poll the failure would evaporate,
and it has to still be there hours later when someone next looks.

Only sessions in the pin ledger are counted: subagents fire SessionEnd too and
always fail (they have no transcript of their own), but they never write a ledger
entry, which is what separates them from real sessions. Dismissals live in
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

**Selecting one room adds a `✎ say` button**, which opens a composer addressed to the
whole room rather than to a window. It appears only for a single named room — `any` and
`solo` name nothing a message could be sent to, and offering it there would invite a
fan-out across the boundary a room is.

The room composer behaves differently from the pane composer, and the difference is
worth knowing before you use it. Every member is checked *before* any of them is
written to, and a member sitting on a permission prompt is **refused rather than sent
into**: text typed into that window would be discarded and the Enter after it would
answer the prompt instead. One unreachable member refuses the whole message, because a
half-delivered announcement makes the silence of the members who missed it
indistinguishable from a considered "not mine". `deliver to whoever is reachable`
overrides that and records who missed it; `check only` runs the whole check and sends
nothing.

The ordinary pane composer keeps no such check, deliberately — it types into the window
you are watching, where answering a permission prompt yourself is the point.

**Per-session controls live on the session's own row**, revealed by opening it —
opening a row is the operator expressing intent about that session, and that
discontinuity is what guards the controls rather than putting them out of reach.
The two are the same size and differ by outline, because shipping the more final
action as the smaller target is how a mis-tap happens.

- **restart** replaces a window's claude process. MCP servers and hooks arm *per
  process* (lab/001), so this is how a wiring change actually takes effect. It
  sends `/exit` — which fires SessionEnd, so the session distills to memory
  normally — waits up to 4 minutes for it, then respawns the window with its
  original command and `THALAMUS_SCOPE` intact. Only a session that hangs past the
  budget gets force-killed, and that one skips distillation. A window that has
  ended offers **revive** in the same place.
- **close** ends a session the same graceful way and removes its window. The
  anchor (the lowest-indexed window) can't be closed: it's the console's reference
  directory and the last thing keeping the roster non-empty.

**⚙ is the admin sheet**, and it holds what is not a per-session act:

- **roster sync** is idempotent backfill — it adds windows the pin ledger expects
  and touches nothing already running.
- **restart all** recycles every window in sequence, which is N irreversible losses
  behind one confirm. It sits in its own section with its own shape rather than
  beside `roster sync`, and its confirm enumerates the count and the groups it will
  hit, read from the same grouping the roster renders.
- **Launch posture** sets what a *newly launched* session starts with, per harness,
  from the ordered options that harness declares (`harness/launcher.py`). Each option
  shows what it gives up, because a posture can only be weighed against its cost if
  the cost is on screen. There are no free-text fields anywhere in this section: a
  value nothing can check is a policy the panel cannot promise to honour.

  A posture looser than the harness's default takes two taps — the rung, then either
  a lifetime (`for 1 day`) or `until I turn it off`. Given a lifetime it **reverts on
  its own**; the expiry is offered rather than forced, because this panel is passed
  through often enough that the setting is re-decided in the normal course of work.
  Tightening is one tap and is refused a lifetime outright — a posture reverting
  toward *more* permission on a timer is the same failure with its sign flipped.
  Every change lands a row in `~/.thalamus/launch/policy.jsonl` with its direction,
  so "when did this box become permissive" has an answer.

  Flags ride the argv and the argv is fixed when a window is created — a recycle
  re-runs the *creation* command — so a posture change cannot reach a running session.
  Windows still on an older argv are badged **old posture**, and the restart button on
  the same row is the fix.
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

Keystrokes are coalesced before they leave the browser, and a held key is the case
that forces it: repeat fires at roughly 30/s, sends are serialised to preserve
order, and one request per repeat would still be draining after the key came up.
Typed characters batch into one send per 24ms window; a run of the same named key
becomes one request carrying a count, replayed inside tmux with `send-keys -N`.
So holding backspace costs a couple of round trips rather than a hundred. The
count is clamped server-side as well as client-side — it arrives over an
unauthenticated loopback API, and nothing reachable there should be able to ask
for unbounded work.

With `--frames`, the desktop surface can also render the pane inside a panel drawn
in a background image — `frame` toggles (F12), `▸` cycles (F9). Off by default, and
when it is off neither the controls nor the key bindings exist; no artwork ships
with it. See [frame-themes.md](frame-themes.md).

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

### Deploying

The unit runs `.venv/bin/thalamus` out of a checkout, and that venv is an editable
install: the console serves `src/thalamus/console/` from that checkout's working
tree. Two things have to move for a merge to reach the phone, and they cover
different halves. The checkout updates `static/` — `app.js`, `style.css` and
`index.html` are read from disk per request, so the client half goes live the moment
the files change. The restart updates `server.py`: the Python is loaded once at
process start, so a merged API change stays invisible until the unit recycles no
matter how current the tree is. A client built against a server field the running
process does not return renders as *nothing happened*.

Both moves are one action. **INFRA → Build → deploy** fast-forwards the checkout onto
its upstream and restarts the unit hosting the console, then the page reloads onto
what it now serves. By hand it is the same two commands:

```bash
git -C ~/code/thalamus pull --ff-only
systemctl --user restart thalamus-console
```

Deploy refuses rather than improvises. Uncommitted changes to tracked files, a
detached HEAD, a branch with no upstream, and a history that will not fast-forward
each stop it with git's own message and the checkout untouched — it stashes nothing,
discards nothing and merges nothing. A refusal is always something to go and fix, not
something to retry.

**Nothing here relies on remembering to check.** The console fetches the checkout's
remote every ten minutes (`--fetch-interval`) and serves what it is running at
`/api/build`: branch and commit, whether the tree is dirty, how far it is behind its
upstream, and whether the running process predates the code on disk. When either of
the last two is true, a bar appears above the roster saying which, with the deploy
button beside it; dismissing it is keyed to the commit, so the next merge raises it
again. The INFRA sheet states the commit whether or not anything is wrong with it,
alongside how long the process has been up and when the remote was last heard from.

A fetch moves remote-tracking refs and touches nothing else — no working tree, no
branch, no index — so it is safe against a checkout other sessions are working in.
`--fetch-interval 0` turns the thread off, and `behind` then means only "behind as of
whenever somebody last fetched".

The service worker is not a suspect in a stale surface: the shell is fetched
network-first, so a reload always takes the newest files the server hands out.

The checkout the console reports on is the one its **code** is imported from, which is
not necessarily `--project-root`. That flag says where roster sync runs; this is a
fact about which tree produced the process answering the request. Installed from a
wheel rather than a checkout, `/api/build` reports `vcs: false`, there is nothing to
fast-forward, and the deploy button is not offered.

### The voice unit

`say` needs a second unit. It holds a neural TTS model resident and answers on
loopback; the console proxies to it.

```ini
# ~/.config/systemd/user/thalamus-voice.service
[Service]
Environment=HF_HOME=%h/.cache/huggingface
ExecStart=%h/.local/share/thalamus-voice/venv/bin/python \
    %h/code/thalamus/src/thalamus/voice/daemon.py \
    --host 127.0.0.1 --port 8380 --device cuda
AllowedCPUs=2-3
Nice=5
Restart=on-failure
```

Three things about it are deliberate:

- **Its own venv, outside the checkout.** torch and a CUDA build do not belong in
  the package's environment. `uv pip install` writes into whatever `VIRTUAL_ENV`
  the calling shell exports, which is how a GPU stack lands in a checkout nobody
  meant to put it in — clear that variable before installing here.
- **A separate process from the console.** The console restarts itself on demand
  and is stdlib-only by design; a GPU-resident model has the opposite lifecycle.
- **Pinned to two cores.** Synthesis runs on the GPU but the Python around it does
  not, and torch helps itself to every core it can see. On a four-core box also
  running the roster, ttyd and a media stack, `AllowedCPUs` is what keeps a long
  utterance from being felt in the terminal. `torch.set_num_threads(1)` in the
  daemon is the other half.

Model load is most of the cost — about 2.3s, against ~0.02 real-time for
synthesis once warm — so the daemon loads at start and synthesises a throwaway
word before it listens. That second step is not a smoke test: the voice tensor is
fetched separately from the model on first use, so a pipeline that has only been
constructed still owes a network round trip, and a box that is offline when the
first tap arrives would fail outright.

The console reaches it at the URL passed to `--voice` (or `$THALAMUS_VOICE_URL`,
which supplies that flag's default) — conventionally `http://127.0.0.1:8380`. Its
dependencies are the `voice` extra: `kokoro`, `torch` and `numpy`, with a
Kokoro-82M download from HuggingFace on first synthesis, so a first run needs
network. Warming is wrapped: a venv missing one of them logs and starts anyway,
leaving the first request to report the real error rather than killing the unit.

It is never exposed through `tailscale serve` — audio reaches the phone through
the console's own `/api/say`, which the service worker leaves uncached along with
every other `/api/` path.

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
| `--voice URL` | `$THALAMUS_VOICE_URL`, else none | Speech service behind `say`. Without it the control is not shown |
| `--fetch-interval MIN` | `10` | How often to fetch the checkout's remote, so "behind" is a fact rather than a report on the last manual fetch. `0` disables it |

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

- **Stdlib `http.server`, not FastAPI** like `pulse/` and `viewer/`. One of its jobs
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
  performs. Only an interactive session records one: everything a session spawns
  inherits its `TMUX_PANE`, so a `claude -p` run from a Bash tool is a full
  session holding a live window's join key, and last-row-wins would hand it the
  read view.
- **Distillation state is derived from the log, except the one state no log can
  hold.** The SessionEnd hook forks and exits, so there is no lockfile or pid file —
  the state machine is `~/.thalamus/logs/session-end-<sid8>.log`, joined against the
  pin ledger to drop subagent residue (two thirds of the logs on a working box).
  It rides the poll the client already runs rather than getting a loop of its own,
  and is cached against (mtime, size) so a steady-state poll opens no file. States
  are `active`, `stalled`, `error` and `unknown`; a clean `done` deletes its row,
  because success is silent.
  **`extract` has two clean endings and both must be recognised.** The summary line
  (`N extracted, M skipped, K failed`) is one; the other is a session with no
  substantive exchange, which is named, found, deliberately not distilled, and exits
  0 having printed no summary at all. Any future exit path that finishes without a
  summary line will be read as a stall — measured, that miss put two false rows on a
  four-row list. A `✗` failure marker is decided on its own for the same reason: a
  job that records a failure and then dies has failed, not hung.
  **A forced close or recycle kills the window before SessionEnd runs**, so
  `thalamus extract` never starts and no log is ever created — and a state machine
  whose only input is the artifact cannot report the artifact's absence. The console
  is the sole witness, because it is the thing that did it, so it appends a row to
  `~/.thalamus/console/distill-killed.jsonl` at the moment it forces. That row is
  what makes `unknown` distinguishable from success: without it a distillation that
  succeeded and one that never ran are the same pixels. A log that later appears for
  the same session overrules the row — the kill is an expectation, a log is evidence.
- **Errors and killed windows persist until dismissed**, tracked in
  `~/.thalamus/console/distill-dismissed.json`. Dismissal is per occurrence, never
  per class: an error row returns when the session distills again, and a killed
  window returns on the next kill, keyed on that kill's stamp.
- **A row carries what tmux cannot know, joined from the pin ledger by pane id**:
  `project` and `repo_root` (so rows group by the repository rather than by a cwd
  string — a checkout and a directory inside it are one project) and `started` (the
  session's own start, epoch seconds, converted at the boundary from the ledger's
  ISO stamp). Absent where the ledger has no value, never inferred from the cwd.
- **Whether a session is stopped waiting on a human is served, not computed by the
  client.** `harness/dispatch.py` owns what the state means and the harness's
  session descriptor owns the value; the console joins them to a window and reduces
  them to `observed`, `blocked`, `blocked_since`, `activity` and `activity_since`.
  **`observed` is the field to branch on.** Session descriptors are partitioned by
  config directory, so a console can be structurally unable to see a window's
  descriptor — measured on one box, the same roster resolved 7 of 9 windows from the
  host config directory and the complementary 2 of 9 from inside a collaboration. An
  unobserved window is `observed: false` with `blocked: null`, never `false`:
  reporting "not stuck" on evidence that says nothing is the failure the indicator
  exists to remove.
- **The state word is composed by the server, not chosen by the client.** `activity`
  is `idle`, `busy`, or empty when the status is neither — a display word the row
  prints, deliberately not carried as `status`, because a field named for the policy
  value invites a second reading of what the reduction exists to consume. Which
  states are worth a clock is decided in the same place: `activity_since` carries the
  transition stamp for `busy` and is null for `idle`, and the client draws an elapsed
  exactly when the stamp is present. Both are empty on an unobserved row — without a
  descriptor the words are equally unknown, so observability travels as one fact
  about the row rather than as an absence repeated across each field.
- **The lifecycle flags are start stamps, not booleans.** A restart or close in
  flight records the epoch second it began, and `grace_s` rides the same payload, so
  elapsed time is renderable and a flag leaked by a dead worker reports its own age
  instead of saying "restarting…" forever. Nothing computes a percentage: the
  deadline is knowable, the finish is not.
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
- **Every request carries its own timeout.** `fetch` has none by default, and a
  phone supplies every reason to need one — a network handoff, a sleeping radio, a
  tailnet re-handshake. Because the chain is single-flight and its latch clears
  only in the completion callback, one request that neither resolves nor rejects
  would wedge the app until a reload: no transcript item lands again, and the view
  toggle stops repainting because every later poll returns at the latch. Both look
  to the operator like the session paused. A request that cannot finish must fail
  instead of hanging, and a latch held past that deadline is released anyway.

## Troubleshooting

**"connecting" forever.** The server is unreachable — check `curl
127.0.0.1:8378/api/panes` on the host, and `systemctl --user status
thalamus-console` if you unitized it.

**The session looks paused and the view toggle does nothing.** Both are the same
symptom, and the first thing to check is whether it is waiting on you: a question
renders open in `read`, marked waiting, and is answered in `term` with ↑ ↓ and
`⏎`. If nothing at all repaints, the beacon reads "no signal" once a request has
outlived its deadline; the next poll recovers on its own without a reload.

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

1. `curl 127.0.0.1:8378/api/build` — which commit is being served, and whether the
   tree or the process is behind. A change that was merged but not deployed looks
   from the phone exactly like a change that does not work, and this is the only
   step that tells them apart.
2. `curl 127.0.0.1:8378/api/panes` on the host — if this is wrong, nothing else
   matters and the problem is tmux or the console.
3. Load the page in a desktop browser on the same network. If desktop is right and
   the phone is wrong, it is the client, not the server.
4. In the phone's browser, unregister the service worker and hard-reload. The shell
   is network-first, so a stale SW is rare but not impossible.
5. If the phone is a home-screen install, suspect **WebAPK scope**. Android installs
   ignore ports and match on path prefix, so two apps published under overlapping
   paths on one host collide, and the icon can silently open the other one. Keep
   each app's mount path disjoint.

**A restart of the console kills the console.** Restart it through `systemd-run`,
not `systemctl restart` from inside itself — the transient unit escapes the
console's own cgroup, which is exactly what the admin sheet's Services button does.

**tmux 3.4 segfaults on startup.** `window-size manual` set *globally* does it.
`pin` sets it per-window for this reason.

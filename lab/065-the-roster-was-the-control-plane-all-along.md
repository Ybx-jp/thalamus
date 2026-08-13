# 065 — The roster was the control plane all along

**Date:** 2026-08-13 · **Scope:** main · **Build:** `cursor/2026.08.11-e8db854` ·
**Verdict:** Cursor rooms built and delivered to end to end; one standing verdict
partially overturned; one guard identified as missing

The Cursor room decision had been open since 2026-08-10 on a verdict from the
`architect` scope: *"isolation without addressing is the solo arm with extra
directories."* The reasoning was sound and rested on three measured absences — no
`sessions/` roster to partition, no `--name`, no peer-messaging surface. This session
was asked to build rooms anyway, using `tmux send-keys` as the transport. Four
measurements later, two of the three absences turned out to be absences of the
*vendor's* mechanism rather than of the capability.

## 1. The config root is first-class, and the credential does not follow it

The prior finding was that `XDG_CONFIG_HOME` moves Cursor's config root and the
session then reports `Not logged in`, so a room would have to provision credentials.
Both halves needed correcting. The bundle resolves three roots by three different
rules:

```js
function se(){ const e=process.env.CURSOR_CONFIG_DIR; if(e?.trim()) return e;
               const t=process.env.XDG_CONFIG_HOME;
               return t?.trim() ? join(t,"cursor") : join(homedir(),".cursor") }
function ie(){ const e=process.env.CURSOR_DATA_DIR;
               return e?.trim() ? e : join(homedir(),".cursor") }
// auth.json, default branch:  join(XDG_CONFIG_HOME ?? homedir()/".config", e, "auth.json")
```

So `CURSOR_CONFIG_DIR` is resolved **ahead** of `XDG_CONFIG_HOME`, and `auth.json` is
resolved by a function that never consults it. The earlier measurement moved
`XDG_CONFIG_HOME`, which moves the config root *and* the credential together — the
logout was an artifact of the lever, not a property of the boundary.

Measured, in order:

| probe | result |
|---|---|
| `CURSOR_CONFIG_DIR=<tmp> agent status` | `✓ Logged in as …` |
| `CURSOR_CONFIG_DIR=<tmp> agent -p --trust "…"` | ran; `cli-config.json`, `statsig-cache.json` and **`chats/`** appeared under `<tmp>` |
| the same session's pin ledger row | present — so `sessionStart` fired |

Three consequences. The boundary partitions **`chats/`**, which is what `--resume`
reads, so it closes the same cross-read channel `ROOM_OWNED`'s `projects/` closes on
Claude Code. There is no credential to provision. And `hooks.json`/`mcp.json` resolve
from a hardcoded `homedir()/.cursor`, so a member arms the operator's hooks and MCP
servers with nothing linked into the room — the pin row is the proof, since only the
hook writes it. A Cursor room's `ensure_room` is therefore one `mkdir`, and every
absence beside it is checked rather than skipped.

## 2. Addressing exists; it is ours, not the vendor's

`pin._with_room` already writes `THALAMUS_ROOM=<room>` into each window's own argv,
because that is the only carrier that survives the `respawn-window` a console recycle
runs. `#{pane_start_command}` renders it back. So room, scope, harness and address are
all recoverable from the window list for a harness that registers nothing anywhere —
the roster the vendor never provided was already being written, for an unrelated
reason.

The substitute is weaker in one way: a descriptor is written by the session and proves
one exists, while a start command is written by the launcher and proves only that a
window was made to hold one. Liveness is therefore asked of the pane (`#{pane_dead}`),
not inferred from the command being readable. It is stronger in another: it needs no
cooperation from the harness, so it addresses `main` — the member the descriptor
roster has never been able to name.

One incidental: tmux escapes non-printable characters in `-F` output, so a `\x1f`
field separator arrives as the four literal characters `\037` and every line fails to
split. Tabs, with a bounded `split(sep, 4)`.

## 3. The transport works, and the third row of the table holds exactly

Driving a real interactive session in tmux:

| state | text | the following Enter |
|---|---|---|
| idle | lands in the composer | submits it |
| busy | lands in the composer | queues — processed as the next turn |
| waiting | **discarded** | **actuates the highlighted default** |

Row three was measured by doing it. Into a pane showing

```
 Run this command?
 Not in allowlist: uptime
  → Run (once) (y)
```

a message reading `THIS IS A DISPATCHED MESSAGE` was sent. It never reached the model,
and the Enter selected `→ Run (once)`. The command ran. This is the Claude Code hazard
verbatim on a different harness: **the first message to a member is the most likely to
hit a dialog, and a blind send both loses the message and approves something the sender
cannot see.**

## 4. Readiness is the joint that does not port

Claude Code publishes a `status` the session writes about itself. Cursor publishes
nothing, so readiness is read from the visible screen — and the discriminator matters
more than it looks. The obvious one is wrong twice over:

- **Not the footer.** It carries the *selected model's* name — captures from one
  session read `Composer 2.5` and `Auto` — so anchoring readiness there would change
  who is addressable when an operator switches models.
- **Not the arrow.** A ready composer draws `→ Plan, search, build anything` and a
  finished turn draws `→ Add a follow-up`. Matching `→` refuses every idle member.

What separates them is the **hotkey**: a selectable option carries the key that picks
it (`(y)`, `(tab)`, `(shift+tab)`, `(esc or n)`), and no ready screen draws one. An
unrecognized screen is refused, matching the rule dispatch already applies to a status
outside its measured set. `capture-pane` is used here and forbidden for confirming a
reply, and the distinction is real: it truncates to the visible height, so a long
answer reads as no answer — while a modal is drawn *in* the visible height.

## 5. The hook fires before the modal

The `architect` proposed replacing the screen read with a first-party descriptor
bracketed by Cursor's own hooks, and flagged one inference as the thing to measure
first. Measured with a probe hook in a scratch workspace's own `.cursor/hooks.json`
(the operator's config untouched): the `beforeShellExecution` hook logged at
`11:01:15`, and at `11:01:20` the approval modal was still on screen unanswered.

**`beforeShellExecution` precedes the modal.** So the interval between it and
`afterShellExecution` is a first-party, vendor-wording-independent window in which a
modal may be up, and a hook-bracketed readiness descriptor is buildable. Not built
here.

## End to end

```
$ thalamus spawn qe --room probe --harness cursor --session cursorroom
Spawned `qe` in room `probe` in …

$ thalamus dispatch probe "Reply with exactly: DISPATCH-RECEIVED"
dispatch a5f5da19b2ae832f — room `probe`, sender `main`, 1/1 delivered
  → probe-qe   deliverable pane %100   updatedAt unmoved (queued)
```

The member replied `DISPATCH-RECEIVED`, and `~/.thalamus/rooms/probe/cursor/chats/`
held its transcript — inside the room, not in the operator's store. Driven into an
approval dialog, the same room refused:

```
$ thalamus dispatch probe "this must not land"
Dispatch refused: refusing the whole fan-out: 1 of 1 target(s) cannot be delivered
to — `probe-qe` is holding an approval dialog — a send would be discarded and the
Enter would actuate the highlighted default …
```

## 6. The peer channel, and the hole that was not on the list

The architect's answer named the sharpest residual and it was not the guard: **nothing
asserted that a dispatching caller was in the room it addressed.** `--sender` is a free
string, `dispatch.py` never read `resolve_room()`, so a member could dispatch into any
room whose name it knew and the ledger would record it as a member of that room. The
config root partitions what a member can *read*; a shell command reaches any room by
name. **The room was isolated in the direction nobody was walking and open in the
direction the collaboration lives.**

`dispatch.authenticate` closes it from the process's own environment, which the caller
cannot author: a roomless caller is the operator (the console server is long-lived and
in no room, so the broadcast path stays open), a caller inside the room speaks only for
its own scope, and a caller inside a different room is refused unless it passes
`--operator`. The row records `sender_authority` — `process` or `operator` — so a later
reader has the field it would need to be honest about what a row is.

`room-command-guard.sh` is the second line, on `PreToolUse:Bash` and, through an
adapter, Cursor's `beforeShellExecution` (§5 measured that it precedes the modal, so a
denial lands ahead of the prompt). Two rules of unequal strength:

- **Addressing a room by name** is checked against the session's own room, fail-closed.
  The room positional cannot be reliably extracted from a shell string — `thalamus
  dispatch --to qe alpha "msg"` puts it after a flag that consumes the next token — so
  the rule is *does this command name the room it is allowed to name*, and one that
  does not is refused rather than parsed.
- **The raw transport** is blocked outright. There is no "to my own room" form of
  `send-keys` worth allowing: the sanctioned channel pre-flights and writes a row and a
  raw send does neither. This one matches the **verb**, not the binary's spelling,
  because it is the only rule with no second line behind it — a raw send never reaches
  `dispatch`, so `/usr/bin/tmux` or `$TMUX_BIN` would otherwise walk through it.

Live, in a real Cursor room member asked to run `tmux send-keys -t %0 hello`: the
command did not run, the guard's prose reached the model verbatim, and the member
reported *"nothing was sent to tmux pane %0; the hook intercepted the shell invocation
in this Cursor session (room probe)."* The row:

```json
{"ts":"2026-08-13T11:30:51Z","scope":"qe","room":"probe","guard":"room-boundary",
 "verdict":"block","branch":"raw-transport","target":"tmux send-keys"}
```

`contract/boundaries.py` moves `room_boundary.message` on cursor from ABSENT to
PROVIDED, and the Claude Code row's note now names both matchers — the peer channel
outgrew a tool name on that harness too.

**A dispatch row is still not a room edge.** Authentication makes the sender
establishable, not the construct comparable: a dispatch is a broadcast with no single
target, and on Cursor it is the entire collaboration vocabulary rather than an
escalation from a cheaper channel, so one edge would mean different things on the two
harnesses and the number would not say so. `eval/rooms.py`'s exclusion stays, and the
guard's own `peer-command` passes are deliberately not edges either.

## What is still not built

**Option C, the first-party readiness descriptor.** The architect refuses
`capture-pane` as a readiness signal on an argument the shipped code does not answer:
it is a **one-directional falsifier** — seeing a modal proves `waiting`, not seeing one
proves nothing, since the same truncation that makes `capture-pane` wrong for
confirming a reply can hide a dialog below the fold. §5 measured the probe that decides
whether the alternative exists, and it stands: bracketing `beforeShellExecution` and
`afterShellExecution` with our own descriptor would replace a vendor's rendering with
an artifact we author. Not built, so the readiness read remains the weakest joint in
the room.

## Incidental defect found

Three tests read the operator's real launch-posture store through
`launch_argv`'s default, and failed on this box because `cursor` had been set to
`auto-review` in the console at 02:31. The tests were right and their environment was
not; `tests/conftest.py` now isolates the store for the whole suite.

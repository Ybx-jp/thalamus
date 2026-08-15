# D4v2 — the surfaces D4 did not open

D4 redesigned the roster rail. The operator's review named four gaps, and working
them exposed a larger one: **D4 redesigned one surface of a console whose session
information is spread across four**, and proposed a vertical session list without
noticing that a vertical session list already ships, twice.

Measured on the running console at 430×932 through the same-origin iframe rig
(`http://127.0.0.1:8378/` — the bare port serves at `/`, because `tailscale serve`
strips the `/console` mount). Source facts carry `file:line`.

## G0 — there is one list of sessions and it exists three times

| surface | what it shows | where |
|---|---|---|
| rail `.rail` | name, identity hue, changed-pulse | y 41.8–77.2 |
| INFRA `#admin-windows` | name, cwd, room, **state word**, old-posture badge, restart, close | INFRA sheet y 46–396 |
| distill `#distill-list` | scope, dir, **distillation state**, age | **SPAWN sheet**, hidden when empty |

To learn whether `designer` in `~/code/thalamus` is alive, restarting, distilling, or
running under a stale posture, the operator opens the rail, then the gear sheet, then
the plus sheet. D4's critique said "the redesign should take from INFRA, not invent"
and then designed a fourth list. The correct move is subtraction: **one row per
session, carrying its whole life**, and the sheets keep only what is not per-session.

## G1 — identity is not the row's key, and the key the design needs is thrown away

`server.py:625-627` states it in the source: "Scope alone doesn't identify a session:
the same expert can be spawned in several directories." The live roster right now:

```
main       title="main — ~/code/thalamus"
main       title="main — ~/code/thalamus"
qe         title="qe — ~/code/thalamus"
designer   title="designer — ~/code/thalamus"
main       title="main — ~/code/thalamus"
```

**Three tabs named `main`, all with byte-identical `title` attributes.** D4 measured
two; there are now three. `.cwd` never fires because it keys on cwd multiplicity
(`style.css:185`) and all three share one.

The console's disambiguators are already inconsistent about this:

- `wlabel()` (`app.js:1262-1263`) forces `room (cwd_label)` into every destructive
  confirm, with a comment saying "Restart homelab? is ambiguous the moment the same
  expert runs in two projects" — the problem is **named in the source**.
- `transcript.resolve()`'s legacy fallback **refuses** rather than guesses when two
  windows share scope+cwd (`transcript.py:196`) — and surfaces `reason:"unresolved"`.
- The rail does neither. It renders them identically.

**There is no project.** The window dict carries `cwd`, `cwd_label`, `cwd_short` and
nothing else. Two sessions in `~/code/thalamus` and `~/code/thalamus/lab` are one
project and would group as two.

The field exists and is discarded: `session-start.sh:69` computes `repo_root` via
`git rev-parse --show-toplevel`, and the pin-ledger row it writes
(`session-start.sh:134-143`) carries `{session_id, scope, agent, room, forked_from,
cwd, entrypoint, tmux_pane, ts}` — **no repo field**. The console can never learn it.
This is D4's F5 shape a second time: the disambiguating information is computed and
then dropped on the floor.

**Handoff:** add `repo_root` to the pin-ledger row. Grouping by repo rather than by
cwd string is the whole of what "pull the repo out to a different element" needs, and
it cannot be done from what the console is served today.

## G2 — the two silences are indistinguishable

Distillation is the moment memory is written, and it is the console's quietest event.

`distill.py` infers state from a log file; there is no status record anywhere
(`distill.py:1-31`). `_classify` (`distill.py:90-113`) yields `active`, `done`, or
`error`, and **`done` deletes the row** (`distill.py:275-276`) — success is
deliberately silent (`app.js:1294-1298`).

Measured: with nothing distilling, `#distill-sec` is `hidden`, height 0, and
`#spawn-pip` measures **0×0**. The entire surface is absent.

Now the failure path. `close_window()` (`server.py:764-793`) sends `/exit`, polls for
pane death up to `RECYCLE_GRACE_S` = 240 s, and **on timeout calls `tmux kill-window`**
(`server.py:790`), which skips SessionEnd — so no `thalamus extract` runs and **no
log is ever created**. `_classify` only ever sees logs that exist. There is therefore
no error row.

| what happened | what the console shows |
|---|---|
| distilled cleanly | nothing |
| never distilled at all (close timed out, window killed) | nothing |

**A distillation that succeeded and one that never ran are the same pixels.** This is
an absence indistinguishable from a negative — the exact failure class this project
has already named twice in its own decision log, once for Cursor's `external_texts`
("nothing was fetched" vs "we cannot know", 2026-07-29) and once for `cost_usd` in
the same entry. It is here a third time, on the write path for memory itself.

`recycle_window()` has the same hole: timeout → `respawn-window -k` (`server.py:757`),
force, no distillation, window comes back looking healthy.

## G3 — the processes have no clock, and one of them can hang forever

`RECYCLING` and `CLOSING` are bare `set[int]` (`server.py:546-549`). No timestamp.
The 240 s deadline lives inside the worker thread and is never served, so the client
renders `"distilling…"` / `"restarting…"` (`app.js:1221-1222`) as words with no
duration — while the worker is silently racing a clock the operator cannot see.

The survey's note is the sharp one: **a crashed worker leaks the flag permanently.**
The entry is discarded in the worker's `finally` (`server.py:760-761`, `792-793`), so
a worker that dies takes the row's exit with it. The row reads `restarting…` forever
and nothing contradicts it.

Distillation rows *do* carry `age` (`distill.py:286-287`) and a stall clock
(`STALL_AFTER_S` = 1200 s → `error`). So the console already knows how to age a
process; it just does not do it for the two processes that can lose work.

**Handoff:** `RECYCLING`/`CLOSING` become `dict[int, float]` keyed to a start stamp.
That one change makes elapsed time renderable *and* makes a leaked flag self-reporting.

## G4 — the mode readback is already on the wire and nothing reads it

Two permission surfaces exist, and neither closes the loop on a running session.

**The `mode` keycap** (`index.html:170`) sends tmux `BTab` — Claude Code's
permission-mode cycle (`server.py:356-357`). It is **blind actuation**: the console
fires the cycle and cannot see where it landed.

Except it can. `/api/read` already serves `permission_mode`, lifted from the
transcript's `type:"permission-mode"` records (`transcript.py:300, 360-361`), along
with `mode` and `agent`. **No client code consumes any of the three** — `pollRead`
(`app.js:916-955`) reads only `available`, `reason`, `session_id`, `items`, `seq`.

D4's F5 found disambiguating information sitting in the DOM and unreachable. This is
the same shape on the wire: the readback that would turn a blind cycle into a
confirmed setting is already being sent and thrown away by the client.

**The launch posture panel** (`index.html:71-78`) is correct and is not the same
thing — it governs *newly launched* sessions, says so, and cannot reach a running
window. Its ladder for Claude Code is `manual` / `acceptEdits` / `auto`
(`launcher.py:226-265`). `bypassPermissions` is deliberately absent and that is
decision-log-level (`launcher.py:217-219`): it "removes the policy checks measured to
stop prompt injection outright". **Any design offering it is out of bounds** — noted
because my consultation leaning assumed it was on the ladder, and the graph corrected
me before the literature did.

`policy_stale` (`server.py:644-646`) already marks windows launched under an older
posture, rendered as an `old posture` badge — measured live on the anchor `main`.
It belongs on the session row, which is where it already is; it is just in the third
list rather than the first.

### The blocked session, and the closed decision it runs into

A session stopped at a permission prompt is the one state where the system cannot
proceed without the human, and **no per-window indicator exists**. The signal lives
only in the read view (`#read-wait`, `app.js:905-912`).

The cost is in this graph. Two literature-scope threads —
`runs-jsonl-content-addressed-pin` and `lab023-dispatch-pending-confirmation` — record
windows dispatched 2026-08-01 that "launched in manual permission mode, so they stop
at every permission prompt and will not progress unattended"
(`scope:literature:claim:f51a88338f3ceba0`). Both threads are **still open today,
2026-08-14** — thirteen days of a session sitting at a prompt with nothing on any
console surface saying so.

**This runs into a closed decision and the design must respect it.** The 2026-08-11
entry in `docs/index.md` ends: *"The client is held to delegation by a test that fails
if the words `waiting`, `idle`, `busy`, `pane` or `send-keys` appear in its source: a
second policy about who is safe to type into would drift from the first."*

So the client may not compute a blocked state. It does not have to: `dispatch.py`
already computes `waiting` in its pre-flight (`dispatch.py:394-398`) and the status
never reaches `/api/panes`. The design serves that one computation and renders it —
one policy, one owner, delegated — which is the decision's own reasoning rather than
an exception to it. **The operator should still rule on it explicitly**, because it
touches the boundary that entry drew.

## G5 — blast radius is uncorrelated with target size, and inversely placed

Measured geometry of every control in the INFRA sheet:

| control | size (CSS px) | mm | y | class |
|---|---|---|---|---|
| per-window `restart` | 70.2 × 24.9 | 3.95 tall | 144–330 | `admin-act` |
| per-window `close` | **56.7** × 24.9 | 3.95 tall | 190–330 | `admin-act danger-lite` |
| `restart all` | 97.3 × 24.9 | 3.95 | 371 | `admin-act` |
| `roster sync` | 97.3 × 24.9 | 3.95 | 371 | `admin-act` |
| `sweep now` | 83.7 × 24.9 | 3.95 | 521 | `admin-act primary` |
| service `restart` | 70.2 × 24.9 | 3.95 | 851, 897 | `admin-act` |

Three findings fall out.

**Every control is 24.9 px = 3.95 mm tall.** Parhi, Karlson & Bederson (MobileHCI '06,
n = 20, one-handed thumb, distractors at zero spacing) measured 29.9% discrete error
at 3.8 mm and 12.9% at 5.8 mm. 3.95 mm interpolates to roughly **28%**. Every
destructive control in this console is rendered at Parhi's worst tested size — the
size D4 established that WCAG 2.2's AA floor cites Parhi to arrive at.

**`restart` and `close` are 8.8 px apart** (close starts at x = 333.4, restart ends at
x = 324.6) — 1.4 mm of separation between a recoverable act and a final one. And the
*more* destructive control is the *smaller* target: `close` is 56.7 px wide against
`restart`'s 70.2.

**`restart all` and `roster sync` are the same button.** Same width (97.3), same
height, same class, same row, side by side. One recreates missing windows and is
idempotent; the other recycles **every** window sequentially — N irreversible losses
of in-flight agent work behind a single confirm (`app.js:1803-1809`, which suppresses
the per-window confirms). The highest-blast-radius control in the console is visually
indistinguishable from the most harmless one.

**Placement is inverted relative to blast radius.** Service restarts — recoverable in
seconds, `systemd-run --collect` so the console survives restarting itself
(`server.py:992-997`) — sit at y 851–897, prime thumb band. Per-session destructive
controls sit at y 144–330, the band where Le et al. (NordiCHI 2016) measured only
43.3% of top-row targets being reached at all. If deliberate hard-to-reach placement
is a guard, this console guards the wrong thing.

## Where the design goes

One row per session, whole life, grouped by project. Sheets keep what is not
per-session: spawn, launch posture, services, cursor sweep. The board is the Penpot
file `D4v2 console lifecycle`.

## What the literature round changed (ticket `2afeb814ce5f4a49`)

Four of my leanings were corrected and one was refuted outright.

**Silence is measured, and I had it backwards about the risk.** I filed "no
measurement exists for the cost of a silent failure" as an open question. The
complacency literature measures exactly it. Parasuraman, Molloy & Singh (1993, n=24):
detection of an automation failure was **.82 when reliability varied and .33 when it
was constant**, F(1,22)=23.0, p<.0001 — and six of twelve constant-condition subjects
had a ten-minute block at 0% detection. Molloy & Parasuraman (1996, n=36): a failure
occurring **exactly once in 30 minutes was missed 42%** of the time under multitasking
against 12% when monitoring was the only task. **Constancy, not unreliability, is the
hazard.** So G2 is stronger than I argued, and its consequence is not "too many rows"
— it is **too uniform a channel**. A terminal failure must not be drawn like a steady
state.

**The `needs you` pill is passive, and passive is measurably weak.** This is the
refutation. Egelman et al. (CHI 2008) found a passive warning **statistically
indistinguishable from no warning** — 90% phished either way. Anderson et al. (CHI
2015) found warning *content* had no effect on habituation; only **appearance** did,
with visual-processing suppression after a *single* repeated exposure. Bravo-Lillo
(2014): visual salience alone was no better than control, and **only forced
interaction resisted decay**. The pill is right for a roster already under the eye and
insufficient for a session that stays blocked. The escalation path is a separate
decision and is deliberately not designed here.

**Separation is measured; distance from the thumb is not the rule.** Yamanaka & Usuba
(2019) took unintended taps from **5.2% to 0% between 0 and 4 mm of spacing, at no
cost in time**. The shipped `restart`/`close` pair has 1.4 mm. The rule is therefore
separation and shape — guard by discontinuity — not "put dangerous things out of
reach."

**Parhi measures size, not location.** F(1,27)=49.18 for size, **not significant for
location**. My G5 framing that top-band placement makes a control more error-prone is
wrong: it makes it less *reachable* (Le 2016), which is a different claim.

**Progress indication underperforms its reputation.** Villar's 32-experiment
meta-analysis: a constant progress indicator does not reliably beat none (LOR 0.072,
p=.365) and slow-to-fast is *worse* (OR 1.56). Myers 1985 measured preference, not
behaviour. Rule 5 therefore stands on honesty — a percentage nobody can compute must
not be drawn — and not on a measured advantage.

**Two more conventions unmasked**, the same shape as D4's target-size chain. Miller's
own 1968 thresholds are, in his words, "the best calculated guesses by the author";
the ubiquitous 0.1/1/10 s triad traces not to Miller but to a **1991 table that never
cites him**, where the three numbers mean frame rate, animation duration and
unit-task grain — three unrelated quantities fused into a response-time rule. And
Nielsen's heuristics carry his own disclaimer: "we do not currently have empirical
evidence to confirm the value of this new set." Undo is not among the original nine,
and confirmation explains ~2% of his problem corpus.

**Still unanswered:** Q1, the grouping question. The sub-agent covering faceting and
grouped-versus-flat lists for small collections never reported, so **the project-as-
group-header decision rests on the operator's instruction and on the matrix argument,
not on measurement.** It is the one structural choice on this board with no citation
behind it.

### A defect in the exchange record itself

The expert closed the ticket and *then* reported that **three claims in its own closed
answer are falsified and a fourth is overstated** — the silent-failure void, the
"false alarms are worse than misses" claim (actually a PPV-dependent crossover:
Dixon 2007 finds FA-prone worse at PPV≈.56; Wickens & Colcombe 2007 finds the opposite
sign at PPV=.70; Wickens 2009 finds no cry-wolf effect at all across 495 real ATC
alerts), the guarded-controls void, and a Parhi errand with a known null answer.

An agent cannot reopen a closed exchange. So the graph now holds an answer that is
partly wrong, with the corrections living only here — the same provenance hazard D4
recorded when Le et al. arrived after its ticket closed, but worse, because this time
the corrections contradict the recorded answer rather than extending it. **The expert
itself recommends a round 3.** That is an operator decision.

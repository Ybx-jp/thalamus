# D4v2 — session row handoff spec

The implementable half of `lab/d4v2-console-lifecycle.md`. That doc argues the gaps;
this one specifies the thing that closes them. Board: Penpot `D4v2 console lifecycle`.

**One row per session, carrying its whole life, grouped by project.** The rail,
`#admin-windows` and `#distill-list` are three lists of the same sessions that
disagree; this replaces all three. The sheets keep only what is not per-session.

Written by designer, implemented by homelab (operator ruling, 2026-08-15). Field names
below are the interface — where they disagree with the server, the server wins and this
doc is wrong.

## 1. Data contract

Served and verified on the live roster. No client-side derivation of any state; the
client renders what it is handed.

**Per-window, in `/api/panes` → `windows[]`:**

| field | type | meaning | drawn as |
|---|---|---|---|
| `name` | str | scope/expert name | identity line, primary |
| `session_id` | str | join key; `[:8]` joins the distill collection | never a label (§3.2) |
| `project` | str | group key; **empty when the ledger has none** (§3.4) | group header |
| `repo_root` | str | from `session-start.sh:69` via the pin ledger | group header, and the grouping key |
| `cwd_label` | str | existing | identity line, only when it differs from the group |
| `started` | float | epoch seconds, converted from ledger `ts` | `opened 09:14`, identity line |
| `index` | int | tmux window index | collision tiebreaker only (§3.2) |
| `observed` | bool | was a descriptor readable at all (§4.5) | **branch on this first** |
| `blocked` | bool\|null | harness descriptor `status`, the same field `dispatch.py:394` reads. `null` exactly when `observed` is false | `needs you` pill / ordinary state / *not in reach* |
| `blocked_since` | float\|null | epoch, from the descriptor's `statusUpdatedAt`; a true transition stamp, not a heartbeat | `stopped 6h47m ago` |
| `recycling` | float\|null | epoch start stamp | `restarting M:SS` |
| `closing` | float\|null | epoch start stamp | `closing M:SS` |
| `activity` | str | `idle`\|`busy`\|`""` — the word the not-blocked slot draws, composed server-side from the descriptor status. Never carried as `status` (§8) | the `blocked=false` state slot (§4.5) |
| `activity_since` | float\|null | epoch of the status transition — the same `statusUpdatedAt` `blocked_since` reads. Null when the state draws no clock | `busy 6:28` |
| `screen_rev` | str\|int | **opaque** change token for this window's screen — any value that differs when the pane text has changed | the rail's changed-pulse, by comparing it to the previous poll's |
| `policy_stale` | bool | `server.py:644-646` | `old posture` |
| `anchor` | bool | the window the console must never close | `anchor` qualifier |
| `harness`, `room`, `dead` | — | existing | as today |

**Payload-level, beside `windows`:**

| field | type | meaning |
|---|---|---|
| `grace_s` | int | `RECYCLE_GRACE_S`, served not hardcoded. 240 today |
| `distill[]` | list | distillation records, joined onto rows client-side on `session_id[:8]` |

**Each `distill[]` record.** It names itself, because it usually outlives its window
(§4.4) and must render with no `windows[]` entry to draw from:

| field | type | meaning | drawn as |
|---|---|---|---|
| `session` | str | 8 hex, joins `session_id[:8]` | never a label |
| `scope` | str | expert name | identity line, primary |
| `project` | str | group key — same field, same pin row as the window's | group header |
| `repo_root` | str | as above | grouping key |
| `dir` | str | **cwd basename — a display string only** | identity line, never grouping |
| `state` | enum | `active`\|`stalled`\|`error`\|`unknown` — the four that reach the wire | §4.1, §4.3 |
| `op` | enum | `close`\|`recycle` — which path killed it | band wording, `unknown` only |
| `detail` | str | verbatim, single line, capped at 200 chars | opened row only |
| `detail_truncated` | bool | true when the cap bit | truncation marker (§4.6) |
| `updated` | float | epoch seconds — same idiom as `started`, `blocked_since` | — |
| `age` | int | seconds, precomputed | elapsed, where a clock is drawn |

**That enum is the wire, not the classifier.** `console/distill.py` also produces a `done`
state and never sends it — a successfully distilled session is dropped from `distill[]`
altogether. So four values arrive, success is not among them, and `op` rides only
`unknown`. The client cannot receive a success value even in principle, which is what makes
§4.2's silence structural instead of a convention the client has to remember.

**`dir` is never a grouping key.** It is a cwd basename, so grouping on it would file a
session in `~/code/thalamus/lab` under `lab` and one in the checkout root under
`thalamus` — G1's exact error arriving through the other collection. It sits on the
record because it is useful to read, and it looks like it would do for grouping, which
is precisely why this sentence is here. Group on `project`/`repo_root` or, when those
are empty, on nothing (§3.4).

**On `/api/read` only, never the poll (§5.1):** `permission_mode`
(`""`\|`manual`\|`acceptEdits`\|`auto`) and `permission_mode_read`
(`ok`\|`unresolved`\|`pending`\|`no-package`).

**The distill join is the one place the client assembles anything**, and it is a lookup,
not a derivation: match `session_id[:8]`, render the record's own `state`. A row with no
matching record has nothing to say about distillation, which is the success silence of
§4.2. A record whose session has no row still renders — that is the whole point of
§4.4, since the window is gone.

Four rules bind the whole table:

**`""` is not `manual`.** `permission_mode` is empty when no `type:"permission-mode"`
record exists, and the parse covers the whole transcript, so empty means *no such
record*, not *we joined late*. The client must never render a mode it was not given,
and absence must never be read as any particular mode.

**Two clocks, never one slot.** `started` is when this session began; `recycling` /
`closing` / a distill record's own clock are when a *process* began. A row legitimately reads
`opened 09:14` and `restarting 0:42` at the same time. They occupy different positions
and different idioms (§3.1).

**The poll carries no screens.** Measured on the live roster 2026-08-15: `/api/panes`
returned 76.5 KiB for 9 windows, of which 61.2 KiB — **80%** — was `lines`, the full pane
text of all nine, including the eight nobody was looking at. At §4's 1.2 s cadence that is
~50 KB/s sustained to a phone, to draw a roster that needs none of it: `lines` is not in
this table, and the row has never had a use for another window's screen. So the pane mirror
travels on the focused-window request — the same split §5.1 already makes for
`permission_mode` — and the roster poll carries `screen_rev` instead.

`screen_rev` is **opaque by contract**. The client compares this poll's value to the last
one and pulses the rail on difference; it never parses it, and nothing about its format is
promised. A hash, a byte count, a monotonic counter are all equally valid, and swapping one
for another must not be a client change. Comparing two opaque tokens for equality is not
computing state — it is the same shape as the distill lookup in this section, and the one
fact the rail's pulse actually needs.

**The row is handed data, never a URL.** Rendering a session takes only the fields above
and the distill join; a row renderer that fetches anything is fetching a fact this table
should have carried, and it takes the §8 guard down with it — `.status` is a legitimate
name on an HTTP response, so a renderer that can hold a response is a renderer the guard
can no longer read. Polling belongs where it is.

## 2. Geometry

Phone-first, 430 × 932. 1 CSS px = 1 dp.

| element | size | note |
|---|---|---|
| collapsed row | 60 px tall | 9.5 mm — Parhi's low-error band, not his worst |
| terminal row (§4.4) | 60 px + band | height change is the salience channel |
| group header | 44 px | not a target; label only |
| identity bar | 4 px wide, full row height | redundant reinforcement, never the sole carrier |
| destructive control | ≥ 60 × 60 px | opened row only |
| destructive separation | ≥ 25 px (4 mm) | Yamanaka & Usuba 2019 |

Every state is a **word** first. Colour and bar are reinforcement; a row read in
greyscale loses nothing but emphasis.

**Typeface is the claim.** Every real state is IBM Plex Mono. A non-observation — the
console saying it cannot see, rather than reporting what it saw — is *never* monospace:
Plex Sans, italic, dimmed. A reader cannot mistake one for the other, because they do
not look like the same kind of thing, and the distinction costs no colour and survives
greyscale. This carries §4.5 and §5.2.

## 3. Row anatomy

```
│ designer                                    idle
│ opened 18:38 · #7 · old posture
```

Line 1: identity bar, name, state slot (right).
Line 2: `opened HH:MM`, then any standing qualifiers — `viewing` first when this is the
row you are on, then `old posture`, `anchor`, `cwd_label` when it differs from the group's
`repo_root`, and `#index` on collision only. **Mode is not among them** (§5.1).

This lane is everything true of a row that is not its state, which is why `viewing` lives
here and not in the slot (§4.1).

### 3.1 The two clocks

`started` renders **absolute** (`opened 09:14`) on the identity line. Absolute is
deliberate: it is stable across polls so rows do not reflow every second, and it is how
a person recalls a session ("the one from this morning").

Elapsed renders **relative** (`restarting 0:42`) in the state slot, and only for the
three things where elapsed *is* the meaning: recycling, closing, distilling. Never for
`started`.

### 3.2 Identity and collisions

`repo_root` fixes grouping. It does not fix the row: three live windows are scope
`main` in `~/code/thalamus` and after grouping they sit under one header still
byte-identical. `name` + `opened HH:MM` disambiguates them.

Ledger `ts` is 1-second resolution and roster sync spawns in a burst, so two rows in
one group can collide on that string. On collision — and only on collision — both rows
append `· #index`. Precedent is `style.css:185`, where `.cwd` renders on multiplicity
rather than always.

`session_id[:8]` is the join key and never a label. It identifies nothing to a human.

### 3.3 The group header

`project` is the header; the row never repeats it. The header is **client-side and
reversible** — the row carries both `project` and `repo_root`, and grouping is a
render choice, not a schema commitment. This is deliberate: project-as-group-header has
no measurement behind it (the faceting question was never answered), so it is built to
cost a rerender to undo rather than a migration.

**Which field is the key.** `project` when non-empty, else `repo_root`, else the trailing
no-project group (§3.4). Header label is `project`, or `basename(repo_root)` when only the
path is known. Name before path because `project` carries the `THALAMUS_PROJECT` override
and is the only field that can unite a worktree with its checkout: `~/code/thalamus` and
`.claude/worktrees/d4v2` are two repo roots and one project, and an operator holding the
phone is looking for the project.

Name-first is safe here only because the row can disambiguate inside the group. Two
unrelated checkouts that happen to share a basename would land in one group, so a row
whose `repo_root` differs from its group's shows `cwd_label` — the mechanism §1 already
gives it. The group answers *which project*; the row answers *which copy*.

### 3.4 The group with no project

`project` and `repo_root` are empty for any session started before the hook wrote them,
and the row says so rather than inferring one. On the live roster today that is **every
window**, so the list renders as a single group until the roster turns over.

**Do not fall back to `cwd_label` for the grouping key.** Deriving a project from a cwd
string is the exact error G1 names: `~/code/thalamus` and `~/code/thalamus/lab` are one
project and would group as two. A guessed hierarchy is worse than none, because it looks
identical to a real one.

So rows with no project collect in **one trailing group**, and its header is a
non-observation, not a name:

```
   no project recorded                                    9
   these sessions started before the ledger carried one
```

Header in sans italic, dimmed — the §2 typeface rule, because "we were not told" is not
a project name and must not sit in the same voice as `~/code/thalamus`. The second line
appears on this group only.

It is self-liquidating: every restarted session leaves it, and when it empties it
disappears. That is the honest shape for a transitional state — it shrinks visibly as
the migration completes, and nothing has to be cleaned up afterwards.

**`repo_root` may be backfilled. `project` may not.** The ledger records `cwd`, and
`repo_root` is a pure function of it — `git -C "$cwd" rev-parse --show-toplevel`, the same
resolver `session-start.sh:69` already runs. Re-running it over an existing row *derives*
the value that row should have carried, which is not the error this section forbids: the
forbidden thing is inventing a name out of a display string. A row whose `cwd` no longer
resolves stays absent. `project` is never backfilled — it carries the `THALAMUS_PROJECT`
override, and an override the ledger did not record cannot be recovered from anything on
disk. A basename substituted for it would be a guess wearing the group header, which is
the one place a guess is indistinguishable from a fact.

So backfilled rows group by path and label by basename, and join their override-named
siblings only as those recycle. **The failure direction is fixed: under-group, never
over-group.** A roster that splits one project across two groups is missing a relation and
shows it — two headers where the operator expected one. A roster that merges two projects
asserts a relation that does not hold and looks exactly like a correct one. Every fallback
in §3.3 is ordered to fail the first way.

**A board caveat that follows from this:** frame B2 draws three populated groups, which
is true after the roster turns over and not before. The transitional state is drawn
beside it rather than instead of it — both are real, one is temporary.

## 4. States

### 4.1 Steady states — the state slot

| state | renders | source |
|---|---|---|
| starting | `starting 0:03` | existing |
| not blocked | `idle`, or `busy 6:28` | `activity`, `activity_since` (§4.5) |
| blocked | `needs you` pill + `stopped 6h47m ago` | `blocked=true`, `blocked_since` |
| unobservable | *not in reach* — sans italic, dimmed | `blocked=null` (§4.5) |
| restarting | `restarting 0:42` | `recycling` |
| closing | `closing 0:12` | `closing` |
| distilling | `distilling 2:14` | distill `state=active` |
| stalled | `distilling 21:04 · stalled` | distill `state=stalled` |
| distilled ok | **nothing** | **no record at all** (§4.2) |
| observed, no word | **nothing** | `activity=""` with `observed=true` (§4.5) |

`stalled` keeps steady geometry. It is past 1200 s but has not failed and may still
complete; the action is wait-or-intervene, not rerun. Only *terminal* states break the
geometry — that is what keeps the loud channel rare.

**Precedence, because several of these are true at once routinely.** The slot answers one
question — *what does this row need from me, and if nothing, what is it doing?* — so the
order is actionability first, then recency. Highest wins; the rest are not drawn.

| | when | draws |
|---|---|---|
| — | terminal (§4.3) | **not in this chain.** The band takes the row's geometry and the slot ceases to exist |
| 1 | `recycling`, `closing`, starting | `restarting 0:42` / `closing 0:12` / `starting 0:03` |
| 2 | distill `active` or `stalled` | `distilling 2:14`, `· stalled` |
| 3 | `blocked === true` | `needs you` + `stopped 6h47m ago` |
| 4 | `observed === false` | *not in reach* |
| 5 | `activity` non-empty | `idle`, `busy 6:28` |
| 6 | otherwise | nothing |

**A blocked row that is mid-restart shows the restart, and that is deliberate.** The
restart *is* the resolution of blocked, and the operator started it — drawing `needs you`
over it asks for an action already taken. If the restart fails, grace expiry promotes the
row to the terminal band (§4.3), which is a louder channel than the pill, so the failure
path is covered by more than the word that got displaced.

**What is not displaced is the count.** The resting bar counts `blocked === true`, one
served field, with no exception for an operation in flight — a count that excluded
in-flight rows would be the client reducing two fields into a policy claim, which is
exactly what §8 forbids. So the pill can leave the slot while the row is still counted:
precedence reallocates a slot, it never retracts a finding.

Ranks 4 and 5 cannot actually collide — `activity` is `""` whenever `observed` is false
(§4.5) — and they are ordered anyway, because a rule that depends on two fields never
disagreeing is one server change away from being wrong.

**`VIEWING` is not in the slot at all.** It is the only entry that was a fact about the
*reader* rather than the session, and it is the one fact the operator cannot fail to
know — they are looking at that window. Ranked anywhere above the bottom it hides a real
state behind a redundant one, and on the anchor row (viewed, and unreadable from a
room-launched console — a live collision, the first row in the list) it would replace the
row's only honest claim with a word that says nothing. It becomes a line-2 qualifier, first
in that lane, beside `anchor` and `old posture` (§3) — the lane that already holds what is
true of a row without being its state.

**The blocked clock is the state that most needs its duration, measured on this box on
2026-08-15:** window 0 — **the anchor**, the console's own reference window, the one it
must never close and the first row in the rail — was alive, status `waiting`, and had
been stopped at a permission prompt for **407 minutes, 6 h 47 m**. Not a mock and not
the 2026-08-01 threads.

It was the **only** blocked row of the four `main` windows; the other three read
`false` — observed, and fine. So this is not the worst of a bad set: **the row that
needed a human was indistinguishable from the three that did not.** `needs you` is a
state; `needs you, since 6 h 47 m` is the finding. (Its 6 h 47 m is unrelated to its
88.3 h `started` — two clocks. Alive 3.7 days, stuck for the last 6.8 hours.)

### 4.2 Why success stays silent

Success is drawn as nothing, exactly as it ships today. This looks like conceding G2
and is the opposite.

Today silence has two referents — "distilled fine" and "never ran at all" — so it means
nothing. Once `unknown` is drawn and drawn unmistakably, silence has exactly one
referent and success can stay quiet. **Silence becomes meaningful only once the other
silence is removed.** Making success loud instead would put a permanent event on every
row and manufacture the constant channel that measured .33 detection.

### 4.3 Terminal states — the band

Three states are terminal: work is lost or may be lost, and nothing further will
happen without the operator.

| state | band reads | carries |
|---|---|---|
| `state=unknown` | `never distilled — window was killed, SessionEnd never ran` | — |
| `state=error` | `distillation failed` | `detail`, verbatim |
| `recycling`/`closing` > `grace_s` | `restart exceeded 240s grace — the window may be gone` | elapsed |

A terminal row is **structurally different**, not a red word in the same slot:

1. It **loses the state slot** and gains a full-width band below the identity line.
2. Its **height changes**, so the list's silhouette changes — detectable peripherally,
   without reading, and it survives greyscale and colour-blindness.
3. Its identity bar becomes a solid full-height block, not a 4 px rule.
4. It carries a **dismiss** control and will not leave on its own (§4.4).
5. **No motion.** No pulse, no animation. Motion is the channel that habituates
   fastest and nothing measured recommends it here.

The third row is G3's self-reporting leak, and it needs no new detection: a served
`grace_s` and a start stamp are sufficient. A crashed worker that leaks its flag
crosses the deadline on its own and says so, instead of reading `restarting…` forever.

> **Citation under correction.** The salience requirement rests on Parasuraman, Molloy
> & Singh (1993, n=24): detection of an automation failure was .82 when reliability
> varied and .33 when constant, F(1,22)=23.0, p<.0001. The literature expert closed
> ticket `2afeb814ce5f4a49` and then reported that three claims in its own closed
> answer are falsified and a fourth overstated; no reader outside that exchange can
> verify whether this is one of them. Round 3 is filed as Linear THA-6 and not opened.
> The design is drawn on this claim and labelled as resting on it — not restated as
> settled.

### 4.3a The loud channel is only worth what its base rate is

Measured while verifying the join: of four live distillation rows, **two were the
classifier lying**. `thalamus extract` has two clean endings and the classifier knew
one — a session with no substantive exchange is named, found, and deliberately not
distilled (`cli.py:1767-1772`, `sys.exit(0)` with no summary line), so those logs aged
past the 1200 s stall clock and were reported as jobs that died mid-flight. They had
finished correctly and lost nothing. A second ordering defect did the same to a log
carrying a `✗` failure marker but no summary: a recorded failure reported as a hang.
Both are fixed at the classifier.

This matters to the design and not only to the server. The whole argument for a
non-uniform, high-salience terminal treatment is that a failure must not be drawn like
a steady state. That argument is exactly what makes a false alarm expensive: had this
shipped unfixed, **half of everything the loudest channel on the row ever said would
have been wrong.**

The honest position on how expensive is narrower than the folk rule, and worth stating
because the folk rule is tempting: "false alarms are worse than misses" is **one of the
claims the literature expert reported as falsified**. What the evidence actually shows
is a PPV-dependent crossover — Dixon 2007 finds FA-prone worse at PPV≈.56, Wickens &
Colcombe 2007 finds the opposite sign at PPV=.70, and Wickens 2009 finds no cry-wolf
effect at all across 495 real ATC alerts. So the defensible rule is not "false alarms
are the worst thing"; it is that **a loud channel's value depends on its positive
predictive value, and we cannot currently cite a reliable price for getting it wrong.**
Which is a reason to keep PPV high by construction rather than to argue about the cost.

Design consequence, and it is the one already built: the loud geometry stays reserved
for terminal states, `stalled` keeps steady geometry because it may still complete, and
success stays silent. Every one of those keeps the rare channel rare and its precision
high.

### 4.4 Dismissal, and the row with no window

**A record outliving its window is the steady state, not an edge case.** Verified live:
the join produces zero hits today, because every current record belongs to a session
whose window is already gone. So the common terminal row is one with **no entry in
`windows[]` at all**, and it must render from the record alone.

So the record carries its own identity — `scope`, `project`, `repo_root`, `dir`,
`updated`, `age` — from the same pin row that supplies the window's, which is what
makes the two group identically by construction instead of by the client reconciling
them. Without that a terminal row could show a failure but not say whose, which would
be a new absence in the middle of the surface built to remove one.

**The kill record is the sharp case.** It is written *as* the window is destroyed, so
anything it fails to capture at that instant is unrecoverable — there is nothing left
to look it up from afterwards. Its identity is read off the ledger before the
destructive act, not after.

A terminal row with an empty `project` lands in §3.4's `no project recorded` group
beside the live rows. That needs no special case and is the honest answer.

A terminal row **outlives its window** and clears only when the operator dismisses it.
If a killed-window row disappeared on the next poll the failure would evaporate and we
would be back to two silences with extra steps; the row has to still be there hours
later, when someone next looks.

This is the smallest available dose of the only intervention that measured durable:
Bravo-Lillo (2014) found visual salience alone no better than control, and **only
forced interaction resisted decay**. No modal, no interruption — a row that will not
leave until a deliberate act removes it.

The machinery already ships and was already an operator ruling: `distill.py:24-25`
keeps a scrap of state in `~/.thalamus/console/distill-dismissed.json` because "errors
persist until dismissed, per the operator's rule", with `dismiss()` (`:168-183`) and
`POST /api/distill-dismiss` (`server.py:1201-1212`) — "not a window operation — the
window whose session this was is long gone." `unknown` rows flow through the same path.
The row is derived from that file; there is no per-row `acknowledged` field.

**Dismissal is per-occurrence, not "never show me this again."** A dismissed row
returns if the same session fails again — for `unknown`, keyed on the kill stamp, so a
second kill of the same session reappears. That is the honest behaviour: the operator
dismissed a failure they saw, not a class of failure they have not.

### 4.5 The row we cannot see

Session descriptors are partitioned by config dir, and `quick.config_dir`
(`quick.py:131-141`) reads only the dir the reading process is in — deliberately, citing
lab/045: "discovery is the room boundary: a caller inside a room must see its
room-mates and nobody else." So the console is structurally blind to a subset of
windows, and which subset depends on how the console itself was launched. Measured on
one roster at one instant: from the host config dir, 2 of 9 rows were invisible; from
inside the collaboration, 7 of 9. This is a common state, not an edge case.

**Reporting an unreadable session as `blocked: false` would print "this session is not
stuck" on evidence that says nothing at all** — G2's failure class, reintroduced by the
control built to remove it, on the row built to remove it. So `blocked` is a tri-state
and the third value is drawn:

| `blocked` | means | state slot |
|---|---|---|
| `true` | read; stopped for a human | `needs you` + `stopped 6h47m ago`, mono |
| `false` | read; not stopped | the ordinary state word, mono |
| `null` | **no descriptor in reach; we cannot know** | *not in reach*, sans italic, dimmed |

The server carries `observed: bool` alongside, and `blocked` is null exactly when
`observed` is false — one lookup written from a single branch, so the two cannot
disagree. **Branch on `observed` first.**

**The `blocked=false` slot draws `idle` or `busy`** (operator ruling, 2026-08-15). The
word arrives as `activity`, composed server-side from the descriptor status, and the row
prints it. It is not carried as `status`: what the row needs is a word to draw, and what
the server owns is the field that decides which word — §8's guard is that boundary, not
an obstacle to be routed around. `w.command` leaves the slot. A foreground process name
answers *which binary is in front*, which no operator asks of this surface; it was there
because it was already being served.

**A constant word here does not contradict §4.2.** The state slot is not an event
channel — it holds exactly one word at all times (`starting 0:03`, `restarting 0:42`,
`needs you`, *not in reach*). §4.2's silence is the distillation channel, a different
position answering a different question. `idle` adds no channel and moves no base rate:
it replaces a word that was already drawn and said less.

**Which states get a clock is the server's call.** `activity_since` is the descriptor's
`statusUpdatedAt` — the same transition stamp `blocked_since` reads — and it is null
unless the state earns a clock. `busy` earns one — a turn still running when you thought
it had finished is a finding, and the number is the whole of it. `idle` does not, because
a running clock on every idle row is motion on most rows at once (§4.3a). The client draws
the elapsed exactly when the stamp is non-null, as it already does for `blocked_since`, so
the decision stays where the reduction is.

**The stamp is verified, not assumed.** Read live off a roster descriptor on 2026-08-15:
a `busy` row's stamp resolved to the second the operator prompted that session, so it is a
transition stamp and not a heartbeat — the property `blocked_since` already depends on,
holding for the same field on the other branch. The row would have drawn `busy 6:28`.

**Emphasis stays flat.** Both words render in the slot's ordinary mono weight, same as
`starting`. `busy` is not a warning and must not compete with the `needs you` pill —
the loud channel is terminal states (§4.3) and it is worth only what its base rate is.
Should either word ever need differential emphasis, it arrives as a server-supplied
boolean, never as a client comparison against the word (§8, Guard A).

**Unknown is empty, never guessed.** `activity` is `""` when the status is neither
deliverable value, and the slot then draws nothing rather than picking the likelier word.
The two silences cannot be confused: an unobserved row draws *not in reach*, so an empty
slot on an observed row means read, not stopped, and no word for it.

`null` disclaims the **whole state slot**, not one pill inside it: without a descriptor,
`idle` and `busy` are equally unknown. What survives is everything the pin ledger knows
— name, project, `started`, `index`, posture — so a `null` row is a *partially known*
row and reads as one: identity confident, liveness explicitly unclaimed. `activity` is
therefore `""` on every unobserved row, and the slot's one word is *not in reach*.
Observability travels as one fact about the row, never as a null on each of three fields;
if `activity` and `blocked` could disagree about whether the session was visible, the
client would have to reconcile them, and a client reconciling state is a client
computing state.

**Only the state slot dims, and this is a majority-case rule, not a detail.** Which subset
of the roster is unreadable depends on the vantage the console was launched from, and both
sides have been measured: 7 of 9 unreadable from the host config dir, the complementary 2
of 9 from inside a collaboration. So *not in reach* is not a rare row — on some vantage it
is most of the list, and the encoding cannot be designed as an exception. A row that dimmed
whole would make a mostly-unobserved roster read as a failed load, which is a false claim
about the console rather than an honest one about the session. The identity half stays at
full strength: name, group, `opened HH:MM`, `#index`, posture. Exactly one slot goes sans
italic and dimmed, and the row still looks like a session that is there.

A tap explains why, in the server's own words, verbatim: *"The console cannot read a
session descriptor for this window. Descriptors are partitioned by configuration
directory, so a session launched into a collaboration is visible only from inside it
(lab/045)."*

**The blindness belongs to the observer, not the row.** Nothing makes a window
structurally unreadable; the deployed console can read the anchor because the service
unit sets no `CLAUDE_CONFIG_DIR` and both sit outside any collaboration. A console
launched from inside a collaboration would render the anchor as `null`. So the wording
says *the console cannot see*, never *this window is unreadable*.

**This is not terminal geometry.** A `null` row stays 60 px. Nothing is lost, nothing
is racing a clock, no operator act is required — it is a gap in observation, not a
failure. Terminal geometry is reserved for work that is lost or may be lost, and
diluting it would cost exactly what makes it work.

The partitioning itself is not fixed here. Unioning config dirs would cross the lab/045
boundary, which is documented with a stated reason and is an operator question. `null`
is the correct rendering whichever way that goes; the ruling only changes how often it
appears.

### 4.6 Truncation must be visible

`detail` is verbatim and capped at 200 characters server-side, because a
contract rejection or write failure can run to a stack trace and the container is a
phone. When the cap bites, `detail_truncated` is true and the row draws an
explicit marker.

A silently truncated string is the same defect this whole design exists to remove: an
absence the reader cannot distinguish from a complete answer. The marker is not
decoration.

## 5. Permission mode

### 5.1 Mode is not on the row, and that is a measured decision

**The collapsed row shows no mode at all.** `permission_mode` stays on `/api/read`,
which resolves one window on demand; putting it on the poll would cost +63% steady
state — 30 ms to 49 ms across nine windows — on a console that polls continuously on a
phone.

The cause is incidental rather than fundamental, and worth recording so nobody
re-opens this on a wrong premise: the transcript feed's byte-offset cache works, and
the sweep itself is **0.02 ms warm**. The 19 ms is `transcript.resolve()` globbing the
projects directory once per window. Making it cheap would mean caching pane→session
resolution, and a stale entry there is exactly the 2026-08-10 bug that pointed a
window's read view at the wrong session for five hours. Not worth it for a standing
setting.

The design loses nothing important, which is why the fallback was pre-authorized before
the measurement came back. Mode is a **standing setting**; the urgent fact is `blocked`,
which is observed, comes from the descriptor, and costs 0.6 ms. A standing setting can
be something you look at when you open the row.

**And the absence of a mode on a row is never read as `manual`, by anyone, including
the reader.** The operational consequence of `manual` — the session stops at prompts —
is carried by `needs you`, which is observed rather than inferred.

`old posture` (`policy_stale`) is a **different axis** and stays a separate qualifier:
it compares launch posture against current policy, where mode-staleness would be a
claim about the running session. Two staleness claims, drawn as two things.

### 5.2 The readback loop — and what the keycap actually does

The `mode` keycap sends tmux `BTab`, which **cycles**. It does not set. A segmented
picker implies random access the mechanism does not have, and you cannot compute how
many steps to press without knowing where you are.

So the control is state-dependent:

- **Mode known** — segmented picker (`manual` / `acceptEdits` / `auto`). Selecting a
  segment presses `BTab` k times to walk there.
- **Mode unknown (`""`)** — the picker is unavailable and degrades to a single
  `cycle mode` button that advances one step, which is exactly what the hardware does.
  After one confirmed readback the picker becomes available.

Either way the act is not finished when the key is sent. The target enters
**unconfirmed** — outlined, not filled, reading `awaiting readback` — and resolves to:

| outcome | condition | renders |
|---|---|---|
| confirmed | readback matches target | filled segment |
| unconfirmed | still `""` after N polls | `could not confirm — mode unchanged on screen?` |
| unreadable | `permission_mode_read != ok` | `cannot read this session's mode (<reason>)` |

That third row is why `permission_mode_read` exists: "no record exists" and "we could
not read this session" are different facts. `unreadable` is drawn **only in the opened
row**, never collapsed — `pending` is common right after spawn, and rendering it on
every fresh row would build the constant channel §4.2 exists to avoid. The collapsed
row shows states; the opened row shows the instrument's confidence in them.

**`bypassPermissions` is not on the ladder and is not offered anywhere in this design.**
`launcher.py:217-219`, decision-log level.

## 6. Controls and blast radius

### 6.1 Where they live

Per-session destructive controls live **inside the opened row**. Opening the row is the
operator expressing intent about that session, and that is the discontinuity — it
replaces "put it out of thumb reach", which was never the measured rule. Parhi is
significant for size, F(1,27)=49.18, and **not significant for location**; top-band
placement makes a control less *reachable* (Le et al. 2016, 43.3%), which is a
different claim. Frequency of use decides position; separation and shape do the
guarding.

### 6.2 The measured fixes

| shipped today | fix |
|---|---|
| every control 24.9 px (3.95 mm) tall — Parhi's worst tested size | ≥ 60 px for anything that can lose work |
| `restart`/`close` 8.8 px apart (1.4 mm) | ≥ 25 px (4 mm) — Yamanaka & Usuba 2019 took unintended taps from 5.2% to 0% across 0–4 mm, at no cost in time |
| `close` (more final) is the *smaller* target at 56.7 px vs 70.2 px | equal size, differentiated by outline treatment — never the same silhouette as a safe control beside it |

### 6.3 `restart all`

`restart all` and `roster sync` ship as the same button: same width, height, class, row,
side by side. One is idempotent backfill; the other recycles every window sequentially,
N irreversible losses of in-flight work behind a single confirm that suppresses the
per-window confirms.

- `roster sync` stays where it is. It is idempotent and harmless.
- `restart all` **leaves that action row entirely** — different placement, different
  shape, and a confirm that *enumerates*: the count and the projects it will hit, from
  the same grouping the list already renders. It is not a per-session act and appears
  on no row.

Guard by discontinuity, not by distance.

## 7. What leaves the sheets

The point of the design is subtraction. After the row ships:

| surface | disposition |
|---|---|
| `#admin-windows` (INFRA) | **deleted.** Name, cwd, room, state word, posture badge, restart, close are all on the row. |
| `#distill-list` (SPAWN) | **deleted.** Distillation is a state of a session, not a separate list of one. |
| rail | kept — it is a switcher, not a list. Identity hue and changed-pulse stay. |
| INFRA sheet | keeps services, `restart all` (§6.3), cursor sweep. |
| SPAWN sheet | keeps spawn and launch posture — both govern sessions that do not exist yet. |

The test of the whole design: to learn whether `designer` in `~/code/thalamus` is
alive, restarting, distilling, blocked, or running under a stale posture, the operator
opens nothing.

## 8. The one-owner guard

`tests/js/dialogue.test.mjs` protects one invariant: **the server reduces, the client
renders.** The harness session status is read for policy in `harness/dispatch.py:394`
(pre-flight refuses to type into a `waiting` session) and reduced to `blocked` in
`console/server.py:415`. A client that read that field again would be a second policy
about the same fact, and two policies drift — which is exactly why the row is handed
`observed` / `blocked` / `blocked_since` and no status string (§1).

**The enforcement is bound to shape, not spelling** (operator ruling, 2026-08-15). A word
list is a proxy for the invariant and fails in both directions: it false-positives on a
local named `busy` holding `!!w.recycling || !!w.closing` — an in-flight operation,
nothing to do with session status — and it false-negatives on `el.textContent = w.status`,
which reaches past the reduction while spelling none of the words. Anyone re-tightening
these checks should re-read that sentence first; a rule that matches bare identifiers is
the one that was already tried.

The rule stated once: **forbidden is a second reader of a field the server has already
reduced for policy.** Three checks, over extracted client source — the dialogue trio, plus
the renderers that draw a session.

**Keep the extraction list pointed at whatever draws the row.** Renaming a renderer fails
extraction loudly, which is the harness working as designed; a list that simply stops
covering the drawing narrows the guard *silently*, and a guard that passes over a file no
longer containing the guarded code is worse than no guard. §7 deletes the sheets that own
two of today's three renderers, so repointing the list is part of implementing §3 — not a
follow-up to it.

**A. No branching on a status value.** Match predicate shapes, never bare identifiers:

- `===` `!==` `==` `!=` adjacent to a status literal, in either order;
- `case "<status>"`, and `switch` over any expression whose text contains `status`;
- `.includes(` `.startsWith(` `.endsWith(` `.indexOf(` `.search(` `.match(` `.test(`
  taking a status literal — substring sniffing is branching with the `if` hidden. A
  regex over the vocabulary counts as a literal, in either position: `/waiting/.test(x)`
  is the same reading as `x === "waiting"` with the comparison spelled differently;
- an object literal keyed by status literals — a lookup table is an opinion with the
  `if` factored out. **Anchored to key position** (`{`, `,` or line start before the
  literal): unanchored, `LIT\s*:` also matches the ternary `cond ? "idle" : "busy"`,
  which branches on `cond` and not on a status value, and the ruling in §4.5 needs that
  shape to stay legal.

Comments are exempt, full-line only — deciding whether a trailing `//` sits inside a
string literal needs a real parser, and guessing blinds the guard rather than tightening
it. The exemption is load-bearing: §8's own rule cannot be stated in a file forbidden to
write `.status`, and source that may not name its invariant grows contorted comments
gesturing at it.

**B. No status field on a row at all** — `lacks(".status")`, `lacks('["status"]')`. §1
serves no status string on a window, so any occurrence is off-contract by construction.
This is the check that closes the verbatim-render hole, and it closes it by *contract*
rather than by vocabulary: there is nothing there to render verbatim. Guard B bans
reading the policy field, not showing a word — which is why it costs the not-blocked slot
nothing. `idle` / `busy` are authorized there (§4.5) and arrive as `activity`, a display
string the server composes; the row prints it, and no client source names either word.

**B is scoped to the row renderers and cannot widen past them.** `.status` is already a
legitimate name elsewhere in `app.js` for two unrelated fields — a tool call's own
`it.status` and an HTTP response's `r.status`. Applied to anything that fetches, B is an
instant false positive, which is the other half of why §1's last rule holds: **the row is
handed data, never a URL.** A row renderer that grew its own fetch would break this guard,
and that is the guard reporting a design violation, not a bug in the guard.

**C. Mechanism names stay banned as literals** — `\bpanes?\b`, `send-keys`. A different
failure (the client re-implementing tmux delivery, not misreading a status) and so a
different rule. Word-bounded, so `panel` is fine and `api/panes` is not — no renderer
should be naming an endpoint. Its real guard is behavioral — the dialogue posts exactly
once, to `api/dispatch` — and this is a cheap belt on that.

**Explicitly legal. The rebound guard must not break any of these:**

| shape | why it is fine |
|---|---|
| `const inFlight = !!w.recycling \|\| !!w.closing` | server-supplied stamps; a local's *name* is not policy |
| `w.observed ? … : notInReach()` | §1 says branch on this first |
| `w.blocked ? pill : slot` | `blocked` **is** the reduction — branching on it is how it gets rendered |
| `slot.textContent = w.activity` | the server composed the word; printing it is the whole job (§4.5) |
| `d.state === "stalled"`, and all of §4.1 | different field, still one owner: the distill enum (`active\|stalled\|error\|unknown`) is authored by `console/distill.py` for display, has no second reader, and §4.1 *requires* the client to branch on it. Guard A's vocabulary is the harness session status only |

`inFlight` is the better name and stays — as accuracy, not as compliance.

**§4.5's clock rule needs no machinery of its own.** Guard A's vocabulary is the words,
not the field carrying them, so `w.activity === "busy"` — the wrong clock condition — is
equality against a status literal and fails the guard, while `w.activity_since ? …`
passes. Drawing the elapsed off the stamp is the only shape the guard leaves open.

**The vocabulary is not folklore.** It is `DELIVERABLE_STATUSES + (WAITING_STATUS,)` —
`idle`, `busy`, `waiting` — at `harness/dispatch.py:108-109`, hardcoded in
`tests/js/statuses.mjs` because node cannot import Python, and pinned to that tuple from
the Python side by `tests/test_console_js.py`. A status added in Python fails the test
that names it instead of quietly widening the hole.

**What the guard does not catch, accepted knowingly.** Bare-identifier object keys
(`{ idle: … }`) and destructuring (`const {status} = w`). Matching either safely runs
into the same ternary collision that anchored A's fourth check, and quoted keys are the
ordinary form — so both stay uncaught rather than bought with false positives on legal
code. A guard that cries wolf gets widened until it means nothing, which is the failure
mode the word list was already an instance of.

## 9. Not designed here

- **Escalation for a session that stays blocked.** The `needs you` pill is passive, and
  passive is measurably weak — Egelman et al. (CHI 2008) found a passive warning
  statistically indistinguishable from no warning, 90% phished either way. The pill is
  right for a roster already under the eye and insufficient for a session blocked for
  thirteen days. What to do about that is a separate decision.
- **Progress percentages.** Nothing here draws one. Villar's 32-experiment
  meta-analysis finds a constant progress indicator does not reliably beat none (LOR
  0.072, p=.365). Elapsed time is honest and computable; a percentage is neither.
- **The client implementation.** Homelab's, from this spec (operator ruling). §8 states
  the guard it has to satisfy; how the checks are written is homelab's call.

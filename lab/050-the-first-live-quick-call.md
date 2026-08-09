# 050 — The first live quick call, and the four things it broke

`thalamus quick ask homelab "…"` was run against a real live `homelab` session on
2026-08-09, minutes after the launcher was written and the suite was green. It
answered, correctly and with citations. It also broke in four places, three of which
no unit test could have caught, because each one is a seam between two components
that were each fine.

The call itself:

| | |
|---|---|
| Wall clock, caller boundary | **88.9 s** (envelope `duration_ms` 83.1 s) |
| Cost | **$0.975** |
| Turns | 8 |
| Output tokens | 4,784 |
| Cache | **318,423 read / 69,643 created — 82% hit** |
| Fresh in-ticket recalls | **3** |
| Parent at fork point | `waiting`, 99 s since last touched |

## The cost figure is the first correction

lab/049 priced a real call at $0.10–$0.52 and a warm one at $0.03–0.08. This call was
warm by every criterion the launcher checks — 82% of its input served from the
parent's cache, the parent touched 99 seconds earlier — and cost **$0.975**.

The warm/cold axis is not what dominates here. 4,784 output tokens at eight turns is
what dominates, and that is the shape lab/049 already found when it measured latency
properly: *wall time per output token is invariant, so which is faster reduces to
which emits fewer tokens*. The same reduction applies to price. A "warm call is cheap"
figure taken on a one-word prompt measures the floor, not the call; **$0.03–0.08 is
the cost of forking, and ~$1 is the cost of answering.** The three mandated recalls
are inside that number.

## 1. The engaged row overwrote the pin row

`assert_ledger` reported that the launcher had met none of its obligations — no
`--agent`, no `THALAMUS_FORKED_FROM` — on a fork whose ledger row carried both,
correctly:

```
{"session_id":"e861ca05…","scope":"homelab","agent":"thalamus-homelab",
 "forked_from":"c8f6d091…","cwd":"…","tmux_pane":"%37","ts":"…"}
{"event":"engaged","session_id":"e861ca05…","scope":"homelab","ts":"…"}
```

`pin-engaged.sh` appends a lifecycle row to the same ledger, carrying `scope` and
nothing else. Last-row-wins — the idiom every reader in the repo uses, correctly, for
*pin* rows — reads `agent` and `forked_from` off the lifecycle row as empty.

`session-end.sh` had the same bug in three places, and its `forked_from` read is the
one that matters: it decides whether a fork distils its delta or its parent's whole
episode. It survived this run only because the env fallback was still set in the
fork's own environment, which a re-extraction from a plain shell would not have. Both
readers now skip rows carrying `event`.

The shape of the failure is worth more than the fix: **a false "clean" and a false
"diverged" are both silent**, and this one reported divergence on a launcher that was
right. Two more rows of this kind and the assertion would have been read as noise.

## 2. The frame break cost the fork its user turn

The delta staged correctly — 47 records out of 112, the parent's 102 filtered out by
UUID — and extraction then declined it: `No session matching e861ca05 under
-home-ybx-code-thalamus`.

`transcripts.parse` counts a `<`-prefixed user record as harness scaffolding rather
than a turn, which is right: system reminders and caveats arrive that way. The quick
prompt opened with `<quick-consultation …>`, so the fork's only user turn was
invisible, `user_turns` was 0, and `extract` skipped the transcript as a
non-conversation.

So the two designs collided exactly where each was correct. The frame break exists
because a bare appended question gets read as an injection into the parent's frame
(lab/049); the `<` rule exists because scaffolding is not a turn. The prompt now opens
with a plain-text line and keeps the tag on the second, and the regression test asserts
against `transcripts.parse` itself rather than restating its rule.

**A protocol that answers and does not distil is the worst of both**: it spends the
money, writes the exchange, and leaves no episode.

## 3. The fork closed its own ticket, ahead of the gate

The design says the ledger row is asserted *before the answer is accepted*. The prompt
told the fork to close with `consult_answer`. The fork did — through the MCP server,
mid-run — so the exchange was `answered` before the launcher's check existed to gate
it. The (false) divergence from §1 was recorded on an exchange that had already closed.

Acceptance is the close, so the closer has to be whoever performs the check. The fork
is now told its reply *is* the answer and not to call `consult_answer`; the launcher
validates citations through the same call. A fork that closes anyway is not fought —
it is recorded, `closed_by: fork`, with the report saying the citations validated and
the ordering did not.

The general form: **a gate the answerer can step around is a report, not a gate.**
Which is fine, as long as the record says which one it was.

## 4. `close_connection()` was called with no argument

Trivial, and listed because of where it landed: the success path, after the fork had
run, the exchange had closed and the graph had been flushed. The call cost a dollar and
printed a traceback instead of an answer. Nothing was lost — the record is the write,
and the record was already written — which is the protocol working as designed on a
day the CLI did not.

## 5. Live is not forkable, and most of the roster is not

Verifying the fixes against a freshly spawned `literature` session failed before the
fork could run:

```
claude -p exited 1: No conversation found with session ID: 16e2eed4…
```

A session registers in `$CLAUDE_CONFIG_DIR/sessions/` the moment it starts and files no
transcript until its **first turn**. So the live roster answers "is this expert
running", and `--resume` asks a different question. The launcher now checks for the
parent's transcript before minting, so an unforkable parent costs nothing, and
`quick targets` prints `no convo` in the status column.

Turning that check on the roster is the finding:

| Live pinned expert session | Age | Forkable |
|---|---|---|
| `homelab` | 10 min | yes — and `busy` |
| `teacher` ×3 | ~16.5 h | **no — never had a turn** |

lab/049 said the roster's normal state is *idle*, and docs/02 answered that a room is a
co-working cluster so warmth is the common case there. Both stand. What the check adds
is sharper and worse for the solo roster: three of four live experts here are not cold,
they are **empty** — spawned, pinned, never spoken to. A quick call against them is not
an expensive call, it is an impossible one. The room argument is now the *only* argument
for availability, and it remains unmeasured.

## 6. A SessionEnd hook that does work in the foreground is cancelled

The delta staging was called synchronously from `session-end.sh`, before the detached
block. It worked on the first fork and not on the second, whose log stops after one
line:

```
distilling session 8d7b6269 into scope literature
```

No staging, no extraction, no error. A headless `claude -p` exits the moment it has
printed its envelope, and a SessionEnd hook still running is cancelled — the same
`Hook cancelled` seen earlier when a fork failed to resume. A few seconds of `uv run`
is enough to lose the race, and losing it is silent.

The hook's own header already says this: extraction runs detached *because* it takes a
minute. Anything that costs time belongs in the same `nohup` block, and the delta
staging now is. Run by hand afterwards, the pipeline was correct end to end: 49 fork
records → 33 staged → one Session in scope `literature`, `forked_from` set, summarising
**the fork's own exchange** and not its parent's episode. The parent has no Session at
all, which is the outcome the whole delta design exists for.

## 7. An open quick exchange is an orphan, and the audit had never seen one

`contract check` reported the unanswered exchange from §5 as an orphan vertex. It is
one, and the tier is why: a full ticket's Exchange is born connected, because every
node the server's brief served becomes a `role: brief` edge — and the quick tier drops
the brief. So until an answer lands its citations, a quick exchange points at nothing.

The audit exempts exactly that shape — `protocol: quick` **and** `status: open` — and
nothing else. An answered quick exchange must still cite, which is the invariant that
was never negotiable. This is the second time dropping the brief has needed a
compensating record (`brief_served: false` was the first): **a projection of the
exchange record is legitimate only where something says which projection it is.**

## What this says about the suite

27 unit tests passed before the first call and after it. They pin the launcher against
fakes: a fake roster, a fake subprocess, a fake graph. **All seven defects live in the
seams the fakes stand in for** — the real ledger's other writers, the real parser's
rules, the real MCP server's availability to the fork, the real harness's
transcript-on-first-turn behaviour, the real hook lifecycle, the real contract audit,
and the real CLI's own signatures.

The corrections are regression-tested now, but the transferable rule is that **the
first live call is the test**, and it should be run against a real expert the day the
launcher is written, not after it is trusted.

## The second call, after the fixes

`literature`, parent primed with one turn, everything green:

| | |
|---|---|
| Wall clock | **27.3 s** |
| Cost | **$0.389** |
| Cache | 62,174 read / 33,531 created — **65% hit** |
| Turns / output | 3 / 886 tokens |
| Fresh in-ticket recalls | **1** — the obligation met and counted |
| Ledger assertion | clean |
| Closed by | **launcher**, with 7 validated citations |
| Delta | 33 of 49 records → one Session in `literature`, `forked_from` set |

Half the wall clock and 40% of the price of the first call, on a third of the output
tokens. Same reduction as before: **the tier's cost is what the expert writes.**

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

## What this says about the suite

27 unit tests passed before the call and after it. They pin the launcher against fakes:
a fake roster, a fake subprocess, a fake graph. All four defects live in the seams the
fakes stand in for — the real ledger's other writers, the real parser's rules, the real
MCP server's availability to the fork, the real CLI's own signatures.

The corrections are regression-tested now, but the transferable rule is that **the
first live call is the test**, and it should be run against a real expert the day the
launcher is written, not after it is trusted.

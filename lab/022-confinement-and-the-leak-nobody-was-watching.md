# 022 — Confinement, and the leak nobody was watching

**Date:** 2026-07-27 · **Component:** eval loop layer 2 (`thalamus eval run`,
`docker/arm-runner.Dockerfile`) · **Status:** both measured leak channels closed;
every confinement property verified live against the built image; **not yet run
against a real arm** — that is the remaining validation and it costs money.

## The leak that was not the one being fixed

lab/020 found two arms reading the operator's task file by absolute path and named
confinement as blocking. Scanning all 88 recorded arms for the *other* way out
found a bigger one:

| channel | arms | visible to lab/021's detector? |
|---|---|---|
| filesystem — absolute-path reads | 3 of 24 | yes |
| **git object store** | **9 of 88** | **no** |

A `git worktree` shares refs and the object store with the operator's repo. An arm
could therefore read the fix, every lab entry describing it, and the task YAML
**without ever naming a path outside its own directory**. Two of the nine are not
incidental:

- `git grep -l "arm-runner-session-death-classification" $(git rev-list --all)` —
  a sweep of every commit in the repository for the task's own id.
- `git show 8b70330 -- tests/test_reader.py` — `8b70330` is the *reader* task's
  own `fix_ref`. That arm predates grading, so the 18/18 acceptance campaigns are
  in scope too, not only lab/020.

The general lesson is the one *Judging the Judges* records for LLM judges, where
style bias (0.10–0.76) dwarfs the position bias the field actually studies
(≤0.04): **the dominant channel was the unstudied one.** Leakage-channel auditing
therefore has to be a standing pre-registered check over an enumerated list, not a
scan run once after someone notices. Current list: filesystem paths, git object
store, network, the live graph over ad-hoc gremlin, `~/.claude` history. The first
four are now closed or detected; the fifth is named and unchecked.

## Layer 1 — a repository that does not contain its own answer

`prepare_worktree` no longer calls `git worktree add`. It builds a private repo
holding exactly the pinned commit:

```
git init <dest>
git -C <dest> fetch --depth=1 \
    --upload-pack='git -c uploadpack.allowAnySHA1InWant=true upload-pack' \
    file://<repo> <full-40-char-sha>
```

Two details are load-bearing. The fetch needs the **full** object name — an
abbreviation is not a fetchable ref — and `allowAnySHA1InWant` has to be set on
the *remote* side of the transport, which `--upload-pack` does without a temp
branch or any config left behind in the operator's repo.

Verified on a real checkout at `1fc6aef`:

| check | worktree (before) | ref-limited repo |
|---|---|---|
| `git rev-list --all` | entire history | **1** |
| `git show <fix_ref>` | full diff | fails |
| `git show master:config/tasks/<id>.yaml` | **the answer key** | fails |
| answer-key sweep across all revs | hits | no hits |
| inherited suite (L1) | 224 passed | **224 passed** |

## The wrong fix, caught by running it

The first version also deleted `config/tasks/` from the checkout, to close
*contemporaneous* leakage — a task authored before the commit it replays ships its
own answer key. That broke the pinned suite: `test_the_shipped_battery_validates`
asserts the battery holds at least two tasks, so **L1 would have failed for every
candidate**. lab/019's ungradeable-design defect, in a new place, and found only
because the arm checkout was actually built and pytest actually run.

The no-regression gate is not a place to hide a harness edit. `refuse_self_leaking_task`
refuses such a task at arm time instead — structural, not a runtime fixup, on the
same ground as the unbuilt arms. All three shipped tasks pass; the check exists to
keep the next one honest.

## Layer 2 — the container, and two runtime facts that had to be measured

`--sandbox` runs the session in `docker/arm-runner.Dockerfile`, mounting the arm's
checkout and a private HOME and **not** the operator's checkout. The toolchain is
mounted from the host rather than baked, so the arm runs the operator's own
`claude` (2.1.220) and `uv` (0.11.28) and the image cannot drift from them.

Two things were assumed and turned out false:

1. **bubblewrap does not work on this box.** `bwrap` is installed and
   `unprivileged_userns_clone=1`, but `kernel.apparmor_restrict_unprivileged_userns=1`
   denies the uid map, and plain `unshare --user` fails identically. Docker needs
   no kernel knob.
2. **Docker Desktop is the wrong daemon.** It is the default context here and runs
   containers in a VM: bind mounts are restricted to configured shares (`/tmp`
   silently denied) and `--network host` is the *VM's* host, so a memory-on arm
   could not reach `ws://localhost:8182/gremlin`. The runner pins the native
   context explicitly.

A third was a bug in the runner rather than the environment: repointing `HOME`
before invoking `docker` broke the *client's* context lookup and produced a
misleading "pull access denied". Only the container's HOME may move.

Verified inside the built image:

```
operator repo  : No such file or directory
arm checkout   : mounted
git history    : 1 commit; git show <fix_ref> fails
claude / uv    : 2.1.220 / 0.11.28   (host parity)
network=host   : graph connects
network=none   : graph refuses
```

## `--isolate-store` closes a question this doc has carried since campaign one

With confinement, `--network none` for an arm carrying no memory surface makes the
graph unreachable. That is docs/04's standing *store isolation for memory-off*
open question — the arm removed the surface, never the store, and a memory-off
session was measured querying the graph over ad-hoc gremlin in the first campaign.

It is opt-in on purpose: it **changes the memory-off treatment**, which is a second
factor, and one-factor-at-a-time is the whole discipline of the arm design. A
campaign using it has to say so in its pre-registration.

The connectivity check is worth recording because two obvious probes both lie: the
image's `/bin/sh` is dash, so `/dev/tcp` is unavailable, and the Gremlin endpoint
is a WebSocket, so an HTTP probe returns `000` from host and container alike. The
signal is curl's *exit code* — 28 (connected, no HTTP reply) versus 7 (no
connection).

## Detection survives, deliberately

An arm reaching for `git log --all` behaves differently from one that does not,
and that is data about the candidate. Closing the channel silently would convert a
measured behavior into an absence. Execution provenance treats environmental
interaction as a first-class step type, so the design is **deny at the
environment, measure at the transcript** — the attempt is still a tool call, and
the rate stays observable after the fix.

`detect_history_reach` reproduces 8 of the 9 measured arms and classifies the
reader arm's `git show 8b70330` as `answer_key`. The two it skips named only their
own pinned ref, which is not a reach — an arm is entitled to inspect the commit it
was handed.

## The predicted failure surface was real, and it was silent

This entry first said the likely failure on first real use was "credentials and
transcript paths, not confinement." The transcript half was already broken when
that sentence was written.

A confined session's `HOME` is the container's, so it writes its transcript to
`<arm-home>/.claude/projects/…`. `transcript_text` read the *operator's*
`~/.claude/projects`, and returns `""` on a missing file rather than raising. A
sandboxed arm would therefore have recorded `transcript_captured: false`,
`recall_calls` `{0, 0}`, every probe a miss and an empty `escapes` list — an arm
that recalled memory perfectly, filed as one that never reached for it.

The direction is what makes it expensive. Confinement exists for *gated*
campaigns, where recall behaviour is the primary outcome (lab/020's C2), so the
bug would have zeroed exactly the measurement the campaign was bought to make, in
the arm where it matters most, while every other field in the record looked
normal. Same class as the `basename $cwd` scoping bug that voided two campaigns
(lab/012) and the `turn_capped` comparison that mislabelled concluded runs
(lab/015): **a default that returns a plausible value instead of failing.**

Fixed by deriving the path in one place — `arm_home_for(worktree)` — so the
mounter and the reader cannot drift, with a test asserting the operator's HOME
does *not* resolve it. Found by reading the code before spending a campaign,
rather than by reading a null result afterwards.

## What is not done

- **No arm has run confined.** Every property above is verified by direct probe of
  the image, not by a campaign. Credentials are the remaining untested surface:
  `.claude.json` is copied into the arm's private HOME, and whether the CLI
  authenticates from that copy inside a container is unverified.
- **Sibling task files** remain readable at refs where they exist (both original
  tasks are present at `1fc6aef`). They do not give away the arm's own answer but
  do reveal how arms are graded. Low severity while probes stay unscored.
- **Prior campaigns are not re-scored.** The stamps are computed going forward;
  lab/020's numbers are corrected in lab/021 but earlier campaigns carry a
  now-known contamination channel that nobody has re-derived.

## Grounding

Literature consultation `scope:main:exchange:3f47831f43f2447b`. The direct prior
art — benchmark contamination in code-agent evaluation — is **not held** by the
`literature` scope, and the expert was explicit that it almost certainly exists,
so nothing here is claimed as novel and docs/11 §4 needs re-checking before it is.

- `scope:literature:claim:eb221c82eff9b517` — execution provenance as the typed
  graph of an agent run, with **environmental interaction** a first-class step
  type. The warrant for deny-and-measure over deny-only.
- `scope:literature:claim:b856fb87d237ac32` — τ-bench grades by comparing end
  state against an annotated goal state; an outcome-state oracle is defeated by a
  candidate that reaches the state by reading the answer, with nothing in the
  verdict to show it.
- `scope:literature:claim:ef4941d93e0a22b8` — `pass^k` over trials presupposes an
  identical start state, which a shared object store does not provide.
- `scope:literature:claim:eecb62f566729b7e` — the dominant judge bias is the
  unstudied one; the argument for an enumerated, pre-registered channel list.
- `scope:literature:claim:3174d0dddc2d5da0` — Fair's flag-don't-exclude stance,
  extended here from harness-caused false negatives to environment-caused false
  positives.

Ranked procurement, demand-driven and still open: SWE-bench solution-leakage work
(arXiv 2410.06992, 2506.12286) as the named prior art; the specification-gaming
canon for vocabulary; Wohlin's threats-to-validity taxonomy for the construct /
internal / external language docs/04 currently improvises.

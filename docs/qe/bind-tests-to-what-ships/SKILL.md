---
name: bind-tests-to-what-ships
description: How to stop a green suite from hiding a broken surface — fakes that grow whatever the code asks for, hand-kept lists that are a second owner, registries that rot in both directions, assertions that pin a timing-dependent spelling, and handing off a finding you are not allowed to fix. Use BEFORE writing a test that constructs its own stand-in for a real type, BEFORE listing field or constant names in an assertion, when a test passes while the running system is broken, and when a suite must stay green while a defect it found stays open.
---

# Bind Tests to What Ships

**A test that constructs its own copy of the thing under test cannot see that thing
drift.** Every pattern here is a variation on it.

## Fakes grow whatever the code asks for

A `SimpleNamespace`, a `Mock`, a local `class Fake:`, a `**kwargs` spy, and a
locally-defined dataclass mirroring a production one all accept any attribute the code
reaches for. So the reduction can read a field the real type does not carry, and the
one shape that cannot fail is the only shape under test.

This ships `AttributeError` on every live call while the suite is green. Reviewers catch
it by reading diffs, which is not a control.

**Pass the real type.** Construct the production dataclass, write the real descriptor
to a tmp dir, drive the real producer. Where the real thing needs substrate, look for
the cheap seam first — a descriptor without `procStart` skips the `/proc` check; a
ledger row is a JSON line in a tmp file. Reach for a fake only when the real type is
genuinely unavailable, and then bind the fake's surface to the real one.

A `**kwargs` spy is the worst case: it accepts arguments the real callee would reject
*and* hides ones it requires. Bind through `inspect.signature(real).bind(...)` so the
stand-in cannot silently diverge.

## A hand-kept list is a second owner

Repairing the above with a list of field names is the same defect with one more name in
front of it. The list is maintained by hand alongside the code it describes, so the day
a fourth attribute is read, the fake grows it and the list never hears about it.

**Derive the names from the code's own source.** Scan the function for `receiver.name`
reads and check each against the real type. A new read is then covered the moment it is
written rather than the day someone remembers.

Deriving found a live repeat immediately: a reduction read three constants off a module,
two were pinned and the third was pinned nowhere but inside the fake — one identifier
away from the defect that had just shipped.

Syntactic scanning is the right tool here. Calling the reduction and observing what it
touches is what the fake already does, and it cannot see an attribute on a branch the
one constructed input never reaches.

Any derived scan needs the control from `verify-before-you-carry`: a scan matching
nothing turns every assertion into a statement about an empty set.

## Registries rot in both directions

A declared list of literals, opacities, or accepted exceptions needs two assertions:

- nothing in the code is missing from the registry — the closure;
- nothing in the registry is missing from the code — the rot.

A row describing something that no longer exists reads as coverage while measuring
nothing, and it fails silently forever. Measurements expire; a table of "colours
measured failing" becomes a table of colours that no longer exist, and the next person
points a fixture at one.

Declare the exception rather than prohibiting the construct. A raw literal is not a
defect — it is the condition that makes defects invisible. Requiring each to be declared
with its role and threshold puts a human decision at the moment one is introduced.

**A role of "carries nothing" is the only one that can stop being true with nothing
changing.** A tint is decorative until the thing it was reinforcing goes away, and no
diff shows that. Record what earns the exemption, and assert *that* — if a control's
dimming is exempt because the state is also carried in text, assert the text is still
rendered.

## Assert the meaning, not the spelling

If the code documents non-determinism, the test may not pin one outcome.

A function returning "(dead, exit status)" documented that a corpse may or may not
survive to carry its status. The test asserted the message contained `exit 1` — the
spelling that appears only when the corpse wins the race — and failed 2 times in 18 on
a loaded box, accusing correct code.

**This class is greppable, and that is the useful part.** Search the implementation for
`depends on timing`, `may or may not`, `both spellings`, `not reliably`, `best-effort`,
`whichever`, `is not evidence that`. For each hit, read the test: if the subject
documents variation and the assertion does not mention it, that is a candidate.

Assert what holds on every path — the failure was reported, the diagnostic text
survived. Where the timing-dependent half is worth covering, drive it somewhere
deterministic by injecting the varying function directly, and assert both branches,
including that an unknown value is not *invented* (rendering "exit 0" for "we could not
tell" is a false reassurance, not a default).

## Handing off a finding you may not fix

When the oracle and the fix belong to different owners, a red suite is not the handoff —
it trains everyone to discount the suite, and the next real failure arrives into an
audience that already ignores it.

Pin the finding as `xfail(strict=True)` with a reason naming the defect, the owner, and
why it is not fixed here. The suite stays green, the finding is recorded where the code
is, and `strict` makes it fail the moment it starts passing, so the marker is removed
rather than left to rot.

Write the assertion so it fails for the right reason. Structural assertions — the real
signature accepts the parameter, the caller passes it — survive the environment; a
behavioural one may pass for an unrelated reason once conditions change.

## Preserve evidence at the assertion

`assert result.returncode == 2` discards the difference between the two ways it fails:
a guard *refusing* and a guard *failing to run*. Those have opposite causes and opposite
fixes, and under `set -euo pipefail` both read as "not 2".

Carry the return code, stdout, and stderr in the assertion message. This matters most
for suspected intermittents, which may appear once: an observed failure whose diagnostic
run happens after it goes green is unrecoverable, and no number of clean re-runs brings
it back.

# How a verdict list becomes a status

A status is never written down. It is derived, every time, by walking the entry's verdicts
in order and taking the status of the last legal one. `claims-ledger status` performs that
walk and prints the result; the library exposes it directly:

    python -c "from claims_ledger import derive_status; help(derive_status)"

## The walk

An entry starts `open`. Each verdict in turn sets the status, until a terminal one stops
the walk. Verdicts that are malformed, that carry a status the schema does not know, or
that restate `open` do not move it.

The terminal statuses are `refuted`, `superseded`, `retracted` and `non-comparable`. Once
one is reached, later verdicts are recorded but do not change the status, and
`claims-ledger validate` reports a verdict appended after a terminal one as malformed. The
single exception is reinstatement: a `refuted` or `non-comparable` entry may be followed
by exactly one `superseded`, because reinstating a claim is done by superseding it.

## What this means in practice

**An entry can leave `contested`.** It is not terminal, so a later verdict moves the
status. That is what makes a contested entry repairable in place rather than only by
supersession.

**Order is the whole of it.** Verdicts append and only append — the region above the
`APPEND BELOW THIS LINE ONLY` marker is immutable once the entry is in version history,
and `claims-ledger validate` compares against history to catch an edit above it. Repair
happens by adding to the end, never by revising what is there.

**A verdict carries who wrote it.** Projects configure which authors may, and one of them
is the propagation author reserved for verdicts the machinery writes. A verdict under that
author carries provenance the checkers hold it to, which is why `claims-ledger freshness
--write` and `claims-ledger propagate --write` exist rather than leaving you to type one.

## Reading an entry's verdicts

    claims-ledger status                          every entry's derived status
    python -c "from claims_ledger import open_ledger, load_entries
    for e in load_entries(open_ledger()):
        print(e.id, e.status(), len(e.verdicts))"

The verdict list is on the entry; each verdict carries its timestamp, status, grade,
author, evidence pointer and note.

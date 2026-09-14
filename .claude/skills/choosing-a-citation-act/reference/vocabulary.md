# The vocabulary, and where to read it

Every list here is exported by the package. Print it rather than trusting a copy — a
project can configure some of it, and this file is a description, not the source.

    python -c "from claims_ledger import STATUSES, ACTS, ENTRY_ACTS, GRADES, KINDS
    print('statuses', STATUSES); print('acts', ACTS)
    print('acts a ground may carry', ENTRY_ACTS)
    print('grades', GRADES); print('kinds', KINDS)"

For the parts a project configures — which evidence types exist, which authors may write
verdicts, which files are documents — ask the loaded configuration:

    python -c "from claims_ledger import open_ledger
    k = open_ledger().config
    print(k.evidence_types); print(k.verdict_authors); print(k.documents)"

## Statuses

A status is derived from the entry's verdict list; it is never stored. `claims-ledger
status` prints what each entry derives to now.

| status | what it says |
| --- | --- |
| `open` | stated, nothing has been recorded against it |
| `corroborated` | a verdict records independent support |
| `contested` | a verdict records a question against it |
| `refuted` | a verdict records that it does not hold |
| `superseded` | a successor entry replaces it |
| `retracted` | its author withdrew it |
| `non-comparable` | it was measured under conditions that do not compare |

The last four are terminal: they stop the walk, so a verdict appended after one does not
move the status. `contested` and `corroborated` are not terminal, so an entry can pass
through either and come out the other side.

## Acts

An act is how a citation names an entry, and it is legal against a set of statuses.

| act | legal against | where it may be written |
| --- | --- | --- |
| `cites-as-live` | `open`, `corroborated` | a document, or an `entry:` ground |
| `cites-as-contested` | `contested` | a document, or an `entry:` ground |
| `cites-as-fallen` | every status | a document, or an `entry:` ground |
| `challenges` | `open`, `corroborated`, `contested` | an `entry:` ground only |
| `distinguishes` | every status | an `entry:` ground only |

Two lists, and the difference between them is the last column. `ACTS` is the **citation**
acts, which is what a document may write inline as `(A0007-a-slug, cites-as-live)` and
what an entry's `## References` rows carry. `ENTRY_ACTS` is what an `entry:` ground may
carry, and it is the citation acts plus `distinguishes`.

`claims-ledger references` states the allowed set in its own findings, which is the
authority when this table and the installed version disagree.

## `distinguishes`

One entry saying of another that the two are about the same artifact and are **different
claims**, with the Warrant saying how. It is not support and not an attack:

- **Legal against every status.** It says something about two Scopes rather than about a
  truth, so no verdict on the target can make it wrong. Grounds are frozen, so an act
  somebody else's verdict could turn illegal would be a failure with no available repair.
- **It propagates nothing.** `claims-ledger propagate` walks `cites-as-live` and
  `challenges`. A target that falls is news about anything that rested on it, and a
  distinction is the statement that this entry did not.
- **It is not support.** An entry whose every ground is one has said what it is not and
  rested on nothing; `validate` reports that, and a `distinguishes` ground is not one of
  the entries motivating a hypothesis either.
- **Only the newer entry can write it.** Grounds are frozen once committed, so the older
  entry never points back. `claims-ledger neighbours` is what reads the relation from the
  other side, and it says so, rather than proposing a pair somebody has already read.

## A parenthesis that is not a citation

`references` reports an id, a comma and an act-shaped word in a document when the word is
not a citation act:

    `(A0007-a-slug, distinguishes)` is shaped like a citation but `distinguishes` is not
    a citation act

The two ways in: a mistyped act, and `distinguishes` written in a document, which is not a
thing a document can do. The rule is narrow — an id in a parenthesis of its own, or named
in running prose, is a document mentioning an entry rather than citing it, and is left
alone. So is a parenthesis whose id the ledger never minted: `(E501, unresolved)` in a
source comment has the shape and names nothing, and a rule that read the shape alone would
refuse a commit over a lint waiver.

## Grades

A grade says how strong the grounds are, and the checkers hold an entry to it.
`claims-ledger new --help` lists them with what each requires; `asserted` forbids an
evidence ground and never goes stale, while `measured` and above require one and take a
pin that `freshness` watches.

## Kinds

`claim`, `prediction` and `hypothesis`. A prediction carries a credence and the
observation that would settle it; an open hypothesis is expected to appear in a roster
document if the project configures one.

## Pointer types

A ground, and a verdict's evidence, is a typed pointer. Four names are reserved across
every project — `entry`, `source`, `search` and `defect` — and the evidence types are
configured. Print `evidence_types` as above to see what this project accepts.

A sectioned evidence type names a span within an artifact and may carry a revision:

    <type>: <path> § "<section>" @<revision>

What counts as a section is a per-project pattern, so the same syntax addresses a
definition in a module, a table in a settings file, or a heading in a document.

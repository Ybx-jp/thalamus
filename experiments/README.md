# Experiments

`lab/` is where vibe research goes: one-page entries in this project's own voice,
written for us, recording what broke and why. **This directory is the other genre.**
An experiment is written for a technical reader outside the project, states what was
committed to before the data was seen, and regenerates every number in it from a
pinned graph state and a seed.

Nothing here may cite the live graph. The graph moves whenever a session ends, and a
number computed against it is not reproducible even by its own author.

## Layout

```
experiments/
  snapshots.jsonl          the pinned-state registry (committed; the .kryo files are not)
  assets/theme.css         design tokens — steel blue leads, warm grey carries
  NNN-slug/
    preregistration.md     written first, never edited after the first run
    run.py                 regenerates results.json and index.html; no other inputs
    results.json           every number the page shows, machine-readable
    index.html             the publication — self-contained, no external assets
```

## The contract for `run.py`

1. Takes `--snapshot`, `--seed`, and nothing that changes a result silently.
2. Serves the snapshot read-only (`thalamus snapshot --serve`) and reads only that.
3. Writes `results.json` **and** `index.html` from the same computation, so the prose
   and the data cannot drift apart.
4. Contains no number that is not computed. If the narrative says a variant wins, the
   sentence is generated from the comparison — a pre-registered hypothesis that fails
   must be able to falsify the page's own text. Experiment 001's did.

## The format

Every page renders these, in this order:

- **The verdict**, labelled `measured`, `null` or `withdrawn`, before any detail.
- **Stat tiles** — each headline number with its interval and its null.
- **The pre-registration**, before the method. This project's is unusually strong:
  the task YAMLs and these files are in git, timestamped by history, and the runner
  refuses violations mechanically. Lead with it.
- **Method and results**, with every rate against its null in the same table row.
  "Used 63% (permuted 57%, κ 0.14)" is a result; "used 63%" is a number.
- **Threats to the result**, including the ones that were declared in advance.
- **The reproducibility checklist**, rendered so that *absence is visible*. After
  Pineau et al., *Improving Reproducibility in Machine Learning Research*, JMLR
  22(164), 2021. An item that does not apply is answered "n/a" with a reason, never
  dropped.
- **What is deliberately absent**, and why. The graph is one operator's session
  history and is never published. An unexplained missing dataset reads as
  concealment; a named threat model reads as a boundary.

## The design system

`assets/theme.css`. Steel blue `#3A7FB5` leads a six-slot categorical ramp; warm grey
is reserved for ink, rules and surfaces, so a grey mark never reads as a category.

The palette was **validated, not chosen**: lightness band, chroma floor,
colour-vision-deficiency separation, normal-vision separation and contrast all pass
against both the light (`#fcfcfb`) and dark (`#1a1a19`) surfaces. Changing a series
hex means re-running that validation.

Figures are hand-emitted SVG whose marks carry CSS custom properties, so one render
is correct in light and dark, and the page stays a single file that survives being
mailed to someone.

## What is here

| # | Experiment | State |
|---|---|---|
| [001](001-the-topic-detector/) | The used-rate is mostly a topic detector | measured; one pre-registered hypothesis falsified, one control withdrawn |
| [002](002-what-the-waste-figure-means/) | What "a third of the tokens are wasted" actually supports | measured |
| [003](003-does-withholding-change-anything/) | Does withholding a memory change what the session does? | pre-registered; accumulating since withholding went live |
| [004](004-the-ceiling/) | A perfect memory, and it made things worse | measured; falsifier fired, layer-2 work cancelled |
| [005](005-framing/) | Reframing the memory did not save it | null; the mechanism 004 proposed is falsified |

003 is the shape this directory is for: the design was committed before a single
observation existed, and its runner reports the empty state honestly rather than
waiting for results to justify a method.

## Running one

```bash
thalamus snapshot --list                      # verify the pinned state and its hash
uv run --extra experiments python experiments/001-the-topic-detector/run.py
```

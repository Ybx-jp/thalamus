<!--
Describe the change and its impact. What changed, what it affects, what a reader
has to do differently, what is still unbuilt.

Constraints, counter-evidence and known gaps stay in, stated as facts. What does
not belong: a narrative of how the work went, or a verdict on it.
-->

## What changed

## What it affects

<!-- Surfaces, callers, anyone who has to do something differently after this lands. -->

## Still unbuilt

<!-- Known gaps this leaves open. "Nothing" is a valid answer. -->

## Verification

- [ ] `uv run pytest`
- [ ] `uv run ruff check src tests`
- [ ] `uv run thalamus contract check` (if a live write path changed)
- [ ] Docs updated in this change (if behaviour a doc describes moved)

---
id: A0172-retrieval-compiler-validates-and-caps-a-job
kind: claim
stated: 2026-09-24T02:00:42-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 080436e768804980629ca85b3375a285749dd56630ece6b0f2f474fc635fde3c
---

## Assertion

The retrieval compiler runs a planner call only when its tool is in the vocabulary, its arguments are the tool's own with values of the declared types and choices, and every node argument is a handle the same job returned; it supplies the job's scope itself, and it refuses the call that would exceed the job's cap on calls or wall time and drops, with a stated line, rows past its cap on distinct nodes or characters of rows. The defaults are 12 calls, 40 nodes, 8,000 characters and 30 seconds.

## Scope

metric: which planner calls reach a vocabulary primitive, with which arguments, and how much a job can return
cohort: calls made through Job.call and Job.word_match in harness/retrieval.py
condition: the MCP wrappers call the primitives directly with vertex ids and are outside this claim

## Grounds

- code: src/thalamus/harness/retrieval.py § "Caps" =sha256:8951f77452ed059d05a82f6564becf1c67b43eb07ead54b37c62061dfc2455e3
- code: src/thalamus/harness/retrieval.py § "TOOLS" =sha256:c5c810be692f72912b029ff2744ec162333ae2d109735d268fcf839b8adb7ca5
- code: src/thalamus/harness/retrieval.py § "Job" =sha256:db7435b5207c3d7dad25786b2fb0b0ba70bc4fa1bca5535cd64584cb92860017

## Warrant

Job._run refuses a name not in TOOLS, a non-object argument set, any key the tool does not declare and any required key missing, and converts each value through _argument, which refuses a wrong type, a value outside the declared choices, a limit outside 1 to MAX_LIMIT, and a handle absent from the job's handle map, substituting the node id for a handle. Only then does _charge run, refusing once the call count or the elapsed time reaches its cap, and the primitive is called with the job's scope added by the compiler; no tool declares a scope parameter. Job.call stops adding rows when a new node would pass the node cap or a line would pass the character cap, and says so. Caps holds the defaults.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T18:02:04-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/retrieval.py § "Job" =sha256:db7435b5207c3d7dad25786b2fb0b0ba70bc4fa1bca5535cd64584cb92860017
  artifact: sha256:6bca52d6c7e18c2d4ec72da98c6b529cc22a69addf794ecdeafc209f09ce1941
  note: propagated from a moved ground
- 2026-09-24T18:02:30-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/retrieval.py § "Job" =sha256:6bca52d6c7e18c2d4ec72da98c6b529cc22a69addf794ecdeafc209f09ce1941
  note: Job gained rows(), the form the propagation plan reads, which passes through the same _run validation and _charge caps and the same node-cap check (now the shared _past_node_cap) and charges no row characters; Job.call and Job.word_match are unchanged in what they validate and cap, and Caps still holds the defaults, so the assertion over its stated cohort is unaffected
- 2026-09-25T02:18:42-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/retrieval.py § "Job" =sha256:6bca52d6c7e18c2d4ec72da98c6b529cc22a69addf794ecdeafc209f09ce1941
  artifact: sha256:5cae7fd8228fdbf7627acb780e15ac607a3b7f3b5cf0cd757023c4179239936a
  note: propagated from a moved ground
- 2026-09-25T02:25:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/retrieval.py § "Job" =sha256:5cae7fd8228fdbf7627acb780e15ac607a3b7f3b5cf0cd757023c4179239936a
  note: Job.call's empty-result string is now the module constant NO_RESULTS, with the same text; validation, scope supply and the four caps are unchanged, so the assertion is unaffected

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/retrieval.py · standing · cites-as-live

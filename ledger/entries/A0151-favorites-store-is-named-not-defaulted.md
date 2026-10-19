---
id: A0151-favorites-store-is-named-not-defaulted
kind: claim
stated: 2026-09-14T11:31:50-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: e37c65360ffbb12c932380ad745753ec16244346d04ab2f49c0d20bb4d7c9094
---

## Assertion

A Config's favorites store is whatever its caller passes; a Config given none reads its own seed alone, and `thalamus console` is the caller that names the machine-global path under the operator's home directory.

## Scope

metric: where a Config's favorites store comes from, and what a Config given none reads
cohort: every Config the console module constructs
condition: where the path comes from; what the store then holds, and that it is the whole list rather than a merge with the seed, are separate claims

## Grounds

- code: src/thalamus/console/server.py § "Config" =sha256:b414e8ae9ec86390e69d284a2075249ed98ed5286839cc80e75abcf5a524bc8b

## Warrant

Config declares favorites_store defaulting to None and its __post_init__ expands the value only when one was passed, so the dataclass introduces no path of its own and a Config constructed without the field carries none — which is what leaves the seed as the only thing effective_favorites can read.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/console/server.py § "Config" =sha256:b414e8ae9ec86390e69d284a2075249ed98ed5286839cc80e75abcf5a524bc8b
  artifact: sha256:3c4c07889839f40bc14a2efbda83e9520544a1df306795b48e972fc75dced976
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/console/server.py § "Config" =sha256:3c4c07889839f40bc14a2efbda83e9520544a1df306795b48e972fc75dced976
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files, and the class docstring was rewrapped. The assertion is unaffected.
- 2026-10-16T17:35:24-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/console/server.py § "Config" =sha256:3c4c07889839f40bc14a2efbda83e9520544a1df306795b48e972fc75dced976
  artifact: sha256:615c62739f84b9ede48022790c3e1b23dd2d205624be4d225c809c22c819c634
  note: propagated from a moved ground
- 2026-10-16T17:45:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/console/server.py § "Config" =sha256:615c62739f84b9ede48022790c3e1b23dd2d205624be4d225c809c22c819c634
  note: `__post_init__` now reads ROSTER_SESSION from console/windows.py; the favorites handling is unchanged. Moved by #342, which takes tmux and room handling out of core into console/; the assertion is unaffected.
- 2026-10-16T21:58:03-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/console/server.py § "Config" =sha256:615c62739f84b9ede48022790c3e1b23dd2d205624be4d225c809c22c819c634
  artifact: sha256:8a2bfc10a4c2ee663584182e29f0c1cb63e882375428134b706326bf78d246c8
  note: propagated from a moved ground
- 2026-10-16T22:10:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/console/server.py § "Config" =sha256:8a2bfc10a4c2ee663584182e29f0c1cb63e882375428134b706326bf78d246c8
  note: Config's project_root default reads paths.CHECKOUT instead of the removed pin.PROJECT_ROOT; the favorites store is untouched. #35 makes an installed wheel resolve its own files and run itself (contract/paths.py). The assertion is unaffected.
- 2026-10-18T22:07:41-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/console/server.py § "Config" =sha256:8a2bfc10a4c2ee663584182e29f0c1cb63e882375428134b706326bf78d246c8
  artifact: absent
  note: propagated from a withdrawn ground
- 2026-10-18T22:10:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: packages/thalamus-console/src/thalamus_console/server.py § "Config" =sha256:8a2bfc10a4c2ee663584182e29f0c1cb63e882375428134b706326bf78d246c8
  note: src/thalamus/console/server.py moved into the thalamus-console plugin package as server.py with Config unchanged, so the assertion is unaffected

## References

- packages/thalamus-console/src/thalamus_console/server.py · standing · cites-as-live
- packages/thalamus-console/src/thalamus_console/commands.py · standing · cites-as-live
- docs/console.md · standing · cites-as-live

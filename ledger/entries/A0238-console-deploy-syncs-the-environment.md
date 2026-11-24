---
id: A0238-console-deploy-syncs-the-environment
kind: claim
stated: 2026-10-25T23:57:23-07:00
author: main
grade: argued
supersedes: A0235-console-deploy-does-not-sync-the-environment
verbatim_change: deploy now syncs the environment after every fast-forward and withholds the restart when the sync fails, where it ran no command that touched the environment; the metric adds whether a unit is named for restart
verbatim_sha: 31ad3a395a5a8775674ec362060ee4048ffbbd2ecda096723414a30576ec4ef6
---

## Assertion

The console's deploy runs `uv sync --inexact --frozen` in the checkout it is served from after every fast-forward, whether or not the checkout moved, when the console is running out of that checkout's `.venv`; a sync that fails or cannot run returns a refusal that names no unit to restart, so the unit is left running rather than restarted into an environment the pulled lockfile does not describe.

## Scope

metric: which commands the console's deploy runs before it returns, and whether it names a unit to restart
cohort: a deploy started from the console's INFRA sheet or its build bar
condition: a console running out of a checkout's editable virtual environment, as docs/console.md's units do

## Grounds

- code: packages/thalamus-console/src/thalamus_console/server.py § "deploy" =sha256:00e8aed02e2d2a80f226e1e5c4961267f4ad914868a6889263ea368e0294f037
- code: packages/thalamus-console/src/thalamus_console/server.py § "sync_environment" =sha256:5115f53584d90b7555cc39578f1423f32351e85191729673301e49e61c35d73a

## Warrant

deploy calls sync_environment after merge --ff-only and before build_info, and returns ok false without a restarting key whenever the result carries an error; sync_environment runs uv sync --inexact --frozen with the checkout as its working directory only when sys.prefix resolves to the checkout's .venv, and reports an error when uv is not on PATH, times out, or exits non-zero. The endpoint restarts only the unit a result names in restarting.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-27T10:14:31-07:00 · contested · grade: argued · author: propagation
  evidence: code: packages/thalamus-console/src/thalamus_console/server.py § "deploy" =sha256:00e8aed02e2d2a80f226e1e5c4961267f4ad914868a6889263ea368e0294f037
  artifact: sha256:eaae9f21a5e0baafcf044e69b99aa2a1a54373efc724d38ce696220bab27a9cc
  note: propagated from a moved ground

- 2026-10-27T10:15:00-07:00 · corroborated · grade: argued · author: main
  evidence: code: packages/thalamus-console/src/thalamus_console/server.py § "deploy" =sha256:eaae9f21a5e0baafcf044e69b99aa2a1a54373efc724d38ce696220bab27a9cc
  note: the failed-sync error's hint now reads `uv sync --inexact --frozen`, matching the command deploy runs; the sync, its ordering and the withheld restart are unchanged

## References

- docs/console.md · standing · cites-as-live
- packages/thalamus-console/src/thalamus_console/server.py · standing · cites-as-live

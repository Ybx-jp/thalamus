---
id: A0235-console-deploy-does-not-sync-the-environment
kind: claim
stated: 2026-10-18T22:11:26-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: b97cf0ddc1ae1f2fced5776c5a518df83deace2ad06b3de03b4b3b2b3e790aa2
---

## Assertion

The console's deploy fast-forwards the checkout it is served from and names the unit to restart, and it runs no command that installs or updates the Python environment, so a merge that changes the lockfile or adds a workspace package reaches the restarted unit only after an operator syncs the environment.

## Scope

metric: which commands the console's deploy runs before it returns
cohort: a deploy started from the console's INFRA sheet or its build bar
condition: a console running out of a checkout's editable virtual environment, as docs/console.md's units do

## Grounds

- code: packages/thalamus-console/src/thalamus_console/server.py § "deploy" =sha256:c1fca813be21c66db8299c34258d1e1e4e32d95fc743e9b1dd4a66c283650e18

## Warrant

deploy calls git status, fetch, rev-parse and merge --ff-only through _git and _git_run, then build_info and self_unit, and returns; nothing in it invokes uv or pip, and the restart its caller performs re-executes the unit's ExecStart against whatever the virtual environment already holds.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/console.md · standing · cites-as-live
- packages/thalamus-console/src/thalamus_console/server.py · standing · cites-as-live

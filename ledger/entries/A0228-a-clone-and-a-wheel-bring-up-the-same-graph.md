---
id: A0228-a-clone-and-a-wheel-bring-up-the-same-graph
kind: claim
stated: 2026-10-16T23:05:01-07:00
author: architect
grade: measured
supersedes: none
verbatim_sha: 75529ab92af5d048e76935b5a61278a3aafd07e0190dab68080c6bface282813
---

## Assertion

The compose file at the top of the clone includes the one the package ships in `src/thalamus/graph/`, and `thalamus graph up`, `stop` and `ps` run that packaged compose file from wherever it was installed, so a clone and a wheel bring up the same graph on the same volume.

## Scope

metric: which compose definition each entry point runs, and which project and volume it resolves to
cohort: `docker compose` from the clone's root and `thalamus graph` from any install
condition: the definition and its naming only; whether the server answers is `thalamus init --check`'s probe

## Grounds

- yaml: docker-compose.yml § "include" =sha256:e35ee39353dad522c787fe68e960423498e408492155612d2ecacc846ef817c3
- yaml: docker-compose.yml § "name" =sha256:5dcc62cbf5c670943acb55fc47d1548ab114c42850d4136b40cef8abd7a5aa10
- yaml: src/thalamus/graph/docker-compose.yml § "name" =sha256:5dcc62cbf5c670943acb55fc47d1548ab114c42850d4136b40cef8abd7a5aa10
- yaml: src/thalamus/graph/docker-compose.yml § "volumes" =sha256:320added99b6b4f443d180e5b3b2ad64f44267493d39e2a89bb18d7af86b9c92
- code: src/thalamus/contract/paths.py § "GRAPH_COMPOSE" =sha256:d2edec7b0dde982131227b7f77047fccb6c4209800fd4ba69626b520d9d37988
- code: src/thalamus/cli.py § "_cmd_graph" =sha256:bed772bec0427a0269d659fb97a725a082dfbb86fb0154460b64934cd819c730

## Warrant

The root file declares project `thalamus` and includes the packaged file; the packaged file declares the same project and the one volume key, and Compose names the volume from the two, so both entry points resolve `thalamus_thalamus-graph-data` (measured with `docker compose config` from each on 2026-10-16). _cmd_graph runs `docker compose -f GRAPH_COMPOSE`, and GRAPH_COMPOSE sits under the package directory, so it is the file an installed wheel carries.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/getting-started.md · standing · cites-as-live

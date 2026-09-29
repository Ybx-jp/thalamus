---
id: A0210-a-codex-profile-forwards-the-pin-to-the-thalamus-server
kind: claim
stated: 2026-09-29T00:30:21-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: f41922ad537116cfe132c4d900c2e6a462e009afd82afe5ceeaa88c62c6b93f5
---

## Assertion

A pinned codex session's thalamus MCP server receives THALAMUS_SCOPE, THALAMUS_ROOM, THALAMUS_FORKED_FROM, THALAMUS_CONFIG_DIR and THALAMUS_ARCHIVE_DIR from the launch, because the scope's generated profile adds them as env_vars to the thalamus server table whenever codex's config.toml registers that server; with no registration the profile adds no thalamus table, and uninstall rewrites the profiles after deregistering.

## Scope

metric: which pin variables reach a codex pin's thalamus MCP server
cohort: profiles written by write_codex_profile into $CODEX_HOME
condition: measured 2026-09-29 on codex-cli 0.154.0 in a scratch CODEX_HOME registered by register_codex_mcp: with the rendered thalamus-qe profile, `env THALAMUS_SCOPE=qe … codex exec --profile thalamus-qe` started the server with all five variables and the registered THALAMUS_GRAPH_URL; without the profile it got THALAMUS_GRAPH_URL alone. A plain codex session with no profile still resolves main, which is its scope.

## Grounds

- code: src/thalamus/harness/pin.py § "CODEX_MCP_FORWARDED_ENV" =sha256:eb8596212f2141506d41f7c8bf80f9fd1ea8f11dbff693cf4c12448851face6f
- code: src/thalamus/harness/pin.py § "_codex_pin_forwarding" =sha256:bacf02182141224cecabe388beb52e0fa701d0da363a2f9ce8856594aa1cd9df
- code: src/thalamus/harness/pin.py § "codex_registers_thalamus" =sha256:cb9576ca52b21248ae82eff44b3c22286739e6ce91148eb039c943ecd1cf72f4
- code: src/thalamus/harness/pin.py § "write_codex_profile" =sha256:43d8f153d00540f970ad02725c0c3dae057d10ac395a300a87f4eed74dd8ef1a
- code: src/thalamus/harness/install.py § "uninstall" =sha256:f2b4f8e0ee705e782ed91ee57944c4b65f0e9b9c819b301ebceec03649e8d283
- entry: A0193-codex-mcp-servers-get-only-allowlisted-env · cites-as-live
- entry: A0211-codex-profile-mcp-table-merges-into-the-registration-and-needs-a-command · cites-as-live

## Warrant

write_codex_profile asks codex_registers_thalamus whether config.toml declares the server and passes the answer to render_codex_profile, which appends the table _codex_pin_forwarding renders from CODEX_MCP_FORWARDED_ENV. A codex stdio server gets only the variables env_vars names (A0193), and a profile table merges into the registered one and needs a command to stand alone (A0211), which is why the table is conditional. uninstall calls write_all_codex_profiles after deregister_codex_mcp.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/pin.py · standing · cites-as-live
- docs/design/launch-templates.md · standing · cites-as-live

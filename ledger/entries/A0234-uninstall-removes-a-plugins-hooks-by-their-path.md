---
id: A0234-uninstall-removes-a-plugins-hooks-by-their-path
kind: claim
stated: 2026-10-18T16:11:31-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: cfbd7a58bd5b9d8d24d3eaab58a0fcc8184c7fe1a3f6b9bcbd47059edc39c725
---

## Assertion

thalamus init wires a hook script a plugin declares only when the script lies under a thalamus_ package's hooks directory for its harness, and thalamus init --uninstall removes every hook entry whose command is a path of that shape, whether or not the plugin that declared it is still installed.

## Scope

metric: which hook entries in the Claude Code user settings file uninstall removes
cohort: hook entries written by thalamus init for a plugin's register_hooks implementation
condition: a plugin's top-level package named thalamus_ followed by lowercase letters, digits or underscores; an operator's own hook whose command happens to be a path of that shape is removed with them

## Grounds

- code: src/thalamus/plugins.py § "PLUGIN_HOOK_PATH" =sha256:05ad50613974e526039e5fb3e2ca55b1e684ef80f199c3c99372cea36deb0494
- code: src/thalamus/plugins.py § "Hook" =sha256:8877a97f64e66c17475cf5504bd740199a589f9ba9afdd5c7a3c5b62b676735c
- code: src/thalamus/harness/install.py § "_is_thalamus_hook" =sha256:c317e5dda119fa1d3c4ea870d2285f88fdf3e67415e99968bd5cda30dfbcb257

## Warrant

Hook.refusal rejects a script whose path PLUGIN_HOOK_PATH does not match, and Plugins.hooks then drops every hook that plugin declared, so nothing install writes for a plugin lies outside the pattern. _is_thalamus_hook, which uninstall's settings stripper applies to every entry, matches the same pattern against the command string and consults no installed plugin. tests/test_install.py installs a fake plugin's hook, removes the plugin, and uninstalls; a mutation that drops the pattern from _is_thalamus_hook fails that test and the existing operator-hook test.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/plugins.py · standing · cites-as-live

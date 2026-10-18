---
id: A0233-a-failing-plugin-costs-only-its-own-commands
kind: claim
stated: 2026-10-18T13:56:07-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: 7887ddcf0a49251a2f7d1e325783c95e4d7e9f8b5581787815a73e48e110ba45
---

## Assertion

A plugin installed under the thalamus entry-point group that fails to load, or whose command registration raises, is reported on stderr and skipped, and the core's commands and every other plugin's commands are still registered.

## Scope

metric: which subcommands the thalamus parser holds after plugin loading
cohort: every distribution installed under the thalamus entry-point group in the environment the thalamus command runs from
condition: covers a failure raised as an Exception while importing the plugin module, while pluggy validates its hook implementations, or while its register_commands runs; a plugin that exits the process or hangs during import is not covered

## Grounds

- code: src/thalamus/plugins.py § "load" =sha256:3b252671b6e21ac5f1e104002da4506040ffaaa55b8f3710fb064c2ce29e0292
- code: src/thalamus/plugins.py § "Plugins" =sha256:9a69e6f2b9b52cbe5d024c68b57b5458eef635cb8060d0627395f9c644ee50a6

## Warrant

load registers each entry point inside its own try block and records a failure rather than raising, and Plugins.register_commands calls each plugin's implementation separately inside its own try block, so one plugin's exception neither stops the loop nor reaches the parser the core built first. tests/test_plugins.py exercises an import failure beside a working plugin, a plugin registering a name core already uses, and a hook with the wrong signature.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/plugins.py · standing · cites-as-live

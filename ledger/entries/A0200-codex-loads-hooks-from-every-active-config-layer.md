---
id: A0200-codex-loads-hooks-from-every-active-config-layer
kind: claim
stated: 2026-09-25T00:49:50-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 4dd5af37d6e51e4bf89f797366e027b25769db0347f2735e3815491a2c26b210
---

## Assertion

codex loads hooks from every active config layer, each as a hooks.json file or as inline hooks tables in that layer's config.toml: the user layer under CODEX_HOME, and a project's .codex directory once that project is trusted. It runs all of them; a hook in one layer does not replace a hook in another.

## Scope

metric: which files a codex session loads hook definitions from, and whether definitions in two layers both run
cohort: codex's hooks documentation as retrieved on 2026-09-25, for codex-cli 0.154.0
condition: measured on codex-cli 0.154.0, 2026-09-25, with five scratch CODEX_HOMEs, no credentials, and a SessionStart hook that touches a file: it fired from CODEX_HOME/hooks.json, from inline hooks tables in CODEX_HOME/config.toml, and from a project's .codex/hooks.json when config.toml marked that project trusted; it did not fire from the same project file untrusted. Runs used --dangerously-bypass-hook-trust, so a hook outside it still needs the operator's review before it runs; a CODEX_HOME/hooks.json hook without the flag and without a trust record did not fire. Plugin-bundled hooks are not covered.

## Grounds

- source: codex-hooks-where-codex-looks · §Where Codex looks for hooks

## Warrant

The section lists hooks.json and inline hooks tables in config.toml as the two forms codex discovers next to each active config layer, names the user and project locations of both, says codex loads every matching hook and that higher-precedence layers do not replace lower-precedence hooks, and says project-local hooks load only when the project layer is trusted.

## Backing

- source: codex-hooks-where-codex-looks · §Where Codex looks for hooks
  speaker: OpenAI
  quote: "Codex discovers hooks next to active config layers in either of these forms:"
- source: codex-hooks-where-codex-looks · §Where Codex looks for hooks
  speaker: OpenAI
  quote: "If more than one hook source exists, Codex loads all matching hooks."
- source: codex-hooks-where-codex-looks · §Where Codex looks for hooks
  speaker: OpenAI
  quote: "Project-local hooks load only when the project `.codex/` layer is trusted."

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/install.py · standing · cites-as-live

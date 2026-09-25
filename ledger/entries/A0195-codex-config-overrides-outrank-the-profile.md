---
id: A0195-codex-config-overrides-outrank-the-profile
kind: claim
stated: 2026-09-25T00:39:55-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 3fd3e1fe1273b99cf9f69f9dd7068167f04979fc9fca4a3653e1d2262b4160c5
---

## Assertion

In codex, a -c override on the command line outranks the profile file --profile selects, so a key set both ways takes the -c value, and a developer_instructions given by -c replaces the profile's rather than joining it.

## Scope

metric: which value codex uses for a key set both by a --profile file and by a -c override
cohort: codex's configuration documentation as retrieved on 2026-09-25, for codex-cli 0.154.0
condition: measured on codex-cli 0.154.0 for model, model_reasoning_effort and developer_instructions: with a scratch home, --profile setting gpt-5.5 and high and the same launch adding -c for gpt-5.6-luna and low, the exec banner showed gpt-5.6-luna and low; `codex --profile thalamus-qe debug prompt-input` showed the qe charter, and adding a -c developer_instructions showed only the override. A 1509-character multi-line charter passed through -c arrived verbatim. tool_output_token_limit and [mcp_servers.*] tables were not measured.

## Grounds

- source: codex-config-precedence · §Configuration precedence

## Warrant

The precedence list ranks CLI flags and --config overrides first and profile files selected with --profile third, highest first, and states one order for every value; the measurement confirms it for the three keys a launch template changes or might carry.

## Backing

- source: codex-config-precedence · §Configuration precedence
  speaker: OpenAI
  quote: […] "1. CLI flags and `--config` overrides" […]
- source: codex-config-precedence · §Configuration precedence
  speaker: OpenAI
  quote: […] "3. [Profile](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles) files selected with `--profile profile-name`" […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/design/launch-templates.md · standing · cites-as-live

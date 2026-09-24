---
id: A0172-budget-output-cap-rides-launch-env-and-codex-profile
kind: claim
stated: 2026-09-24T02:17:06-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 628f259e5b3f6a4e8d134fadf40c880f89d454eba8b259b2ee822f6888f54a9d
---

## Assertion

A budget preset's max_tool_output_tokens reaches a pinned Claude Code session as BASH_MAX_OUTPUT_LENGTH at four characters a token, clamped to 150000, and as MAX_MCP_OUTPUT_TOKENS and CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS, on an env prefix of the launch argv; it reaches a codex pin as tool_output_token_limit in the scope's profile.

## Scope

metric: how the tool-result cap reaches each harness
cohort: pins launched through launch_argv and codex profiles rendered by render_codex_profile
condition: measured 2026-09-24 on Claude Code 2.1.281: with BASH_MAX_OUTPUT_LENGTH=2000, `seq 1 5000` reached the model cut to about 527 lines, and the model read the rest from the file Claude Code saved the full output to; the cap bounds what one result puts in context, not what the session can reach. A subagent inherits its launcher's environment, so it is capped as its launcher is.

## Grounds

- code: src/thalamus/harness/budget.py § "claude_output_env" =sha256:dfb2c995327934d87c1ca986c5d059bd67e0d77bcc074dd773b3b45f7e2762c8
- code: src/thalamus/harness/budget.py § "launch_env" =sha256:7225d507e3db52d11353358cf28251d501b660deb4966ba06316fd14ccab7690
- code: src/thalamus/harness/launcher.py § "launch_argv" =sha256:9903832749283d245cd16744318d8e3e7aca651b35e10620fe099f929590ddd5
- code: src/thalamus/harness/pin.py § "_codex_cost_keys" =sha256:271af7483bf973b1c0a45c95831a002c7290460bd15c274fd618d46bcd5213cc
- entry: A0170-tool-output-caps-are-launch-settings · cites-as-live

## Warrant

claude_output_env maps the preset key onto the three variables, launch_env returns them for Claude Code only, launch_argv prefixes them with env ahead of the binary, and _codex_cost_keys writes tool_output_token_limit into the codex profile. Those are the settings each harness reads its cap from (A0170).

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/budget.py · standing · cites-as-live
- src/thalamus/harness/pin.py · standing · cites-as-live

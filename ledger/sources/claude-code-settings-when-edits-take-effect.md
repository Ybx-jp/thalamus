### When edits take effect

Claude Code watches your settings files and reloads them when they change, so it applies most edits to the running session without a restart, including edits to `permissions`, `hooks`, and credential helpers such as `apiKeyHelper`. Claude Code also loads a settings file you create mid-session if its folder existed when the session started. For the project's `.claude/` folder, it loads the file even when you create the folder in the same session.

The reload covers user, project, local, and managed settings. Claude Code runs the [`ConfigChange` hook](https://code.claude.com/docs/en/hooks#configchange) for direct edits to settings files, not for managed settings that arrive from MDM or the claude.ai console. Managed settings that arrive through MDM or from the claude.ai console reach a running session on a schedule rather than on save; the [delivery table](https://code.claude.com/docs/en/managed-settings.md#choose-a-delivery-mechanism) gives it per source.

Claude Code reads some keys only once, at session start, so an edit to one of them doesn't reach the running session. Admin-side keys that also wait for a restart, such as `requiredMinimumVersion`, are listed under [where and when a policy applies](https://code.claude.com/docs/en/managed-settings.md#where-and-when-a-policy-applies). The ones you're most likely to edit mid-session:

* [`model`](https://code.claude.com/docs/en/settings-reference#model): use [`/model`](https://code.claude.com/docs/en/model-config#setting-your-model) to switch mid-session. Each model has its own prompt cache, so the first request after a switch re-reads the whole conversation uncached; see [Switching models](https://code.claude.com/docs/en/prompt-caching.md#switching-models)
* [`effortLevel`](https://code.claude.com/docs/en/settings-reference#effortlevel) and [`modelSettings`](https://code.claude.com/docs/en/settings-reference#modelsettings): use [`/effort`](https://code.claude.com/docs/en/model-config#adjust-effort-level) to change effort mid-session

If you remove [`permissions.blockReadsOutsideWorkingDirectories`](https://code.claude.com/docs/en/settings-reference#permissions-blockreadsoutsideworkingdirectories) mid-session, the file tools keep the block in the running session. To lift it, remove the key from every settings file that sets it, then restart each running session.


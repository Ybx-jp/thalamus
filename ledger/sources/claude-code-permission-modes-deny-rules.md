## Available modes

Modes set the baseline. Layer [permission rules](/docs/en/permissions#manage-permissions) on top to pre-approve or block specific tools. Deny rules block in every mode, including `bypassPermissions`. Deny and ask rules don't apply to [`EndConversation`](/docs/en/tools-reference#endconversation-tool-behavior) as long as Claude still has at least one other tool it can call. Allow rules have no effect in `bypassPermissions`.

### Environment variables

| `BASH_MAX_OUTPUT_LENGTH` | Maximum number of characters of bash output that Claude Code reads back into a command's result (default: 30000; maximum: 150000). If you set the [`bashOutputMaxChars`](/docs/en/settings-reference#bashoutputmaxchars) setting, Claude Code ignores this variable. See [Output limits](/docs/en/tools-reference#output-limits) |
| `MAX_MCP_OUTPUT_TOKENS` | Maximum number of tokens allowed in MCP tool responses. Claude Code displays a warning when output exceeds 10,000 tokens. Tools that declare [`anthropic/maxResultSizeChars`](/docs/en/mcp#raise-the-limit-for-a-specific-tool) use that character limit for text content instead, but image content from those tools is still subject to this variable (default: 25000) |
| `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` | Override the default token limit for file reads. Useful when you need to read larger files in full |

### codex config reference

key: "tool_output_token_limit", type: "number", description: "Token budget for storing individual tool/function outputs in history.",

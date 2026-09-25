## Configuration precedence

Codex resolves values in this order (highest precedence first):

1. CLI flags and `--config` overrides
2. Project config files: `.codex/config.toml`, ordered from the project root down to your current working directory (closest wins; trusted projects only)
3. [Profile](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles) files selected with `--profile profile-name` (`~/.codex/profile-name.config.toml`)
4. User config: `~/.codex/config.toml`
5. Cloud-managed `config.toml` defaults, when delivered for the signed-in workspace
6. System config (if present): `/etc/codex/config.toml` on Unix
7. Built-in defaults

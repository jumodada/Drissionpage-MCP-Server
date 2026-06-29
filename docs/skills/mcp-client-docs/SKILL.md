---
name: drissionpage-mcp-client-docs
description: Maintain README and public docs for Codex, Claude Code, Cursor, Claude Desktop, screenshots, and MCP client setup.
---

# MCP Client Docs Skill

Use this when updating README/client setup documentation.

## Current documentation shape

The README now owns client setup examples directly. The old `examples/` directory has been removed.

Do not add tests or packaging rules that require:

- `examples/README.md`
- `examples/codex-config.toml`
- `examples/codex-source-config.toml`
- JSON config files under `examples/`

Instead, keep public setup guidance in:

- `README.md`
- `README_CN.md`
- `docs/tool-contract.md`
- `docs/troubleshooting.md`

## README navigation

Top README navigation should quickly route users to:

- install and screenshot walkthrough
- Codex CLI/IDE setup
- Codex integration example
- Claude Code setup
- Cursor setup
- Claude Desktop setup
- troubleshooting

Keep anchors stable when changing headings. If headings change, update the navigation links in both `README.md` and `README_CN.md`.

## Client setup contracts

### Codex CLI/IDE

Codex uses TOML config:

```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

Verification commands:

```bash
codex mcp list
# or in TUI
/mcp
```

For source checkouts, document the source form in `docs/tool-contract.md`:

```toml
[mcp_servers.drissionpage]
command = "python"
args = ["-m", "drissionpage_mcp.cli"]
cwd = "/absolute/path/to/DrissionMCP"
```

### Claude Code / Claude Desktop / Cursor

Use JSON MCP client examples in the README integration section. Keep the command simple for PyPI installs:

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

If a client has a specific UI flow, document it as steps, but keep the JSON command consistent unless the runtime requires otherwise.

## Screenshot guidance

Screenshot images can be useful in README, but keep them supplemental:

- image assets should not replace copyable commands/config
- alt text should describe the command or client screen
- README should still be usable in plain text terminals

## Release metadata test

`tests/test_release_metadata.py` should verify current public docs, not deleted examples. The Codex docs test should read README files plus `docs/tool-contract.md` and `docs/troubleshooting.md`.

Useful expectations:

- `[mcp_servers.drissionpage]` appears in public docs
- `command = "drissionpage-mcp"` appears in public docs
- `codex mcp list` appears in troubleshooting
- `recursive-include examples` is not in `MANIFEST.in`

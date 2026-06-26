# Configuration Examples

This directory contains configuration examples for Codex, Claude, and other MCP clients.

## 📁 Files

### Codex CLI / IDE

- **`codex-config.toml`** - Codex configuration after installing from PyPI
- **`codex-source-config.toml`** - Codex configuration for a source checkout

Codex reads MCP servers from `~/.codex/config.toml`, or from `.codex/config.toml` inside a trusted project. The Codex CLI and IDE extension share this configuration.

### JSON MCP Clients

- **`pypi-install-config.json`** - JSON MCP configuration after installing from PyPI
- **`claude-code-config.json`** - JSON MCP configuration for source/development use
- **`claude-desktop-config.json`** - Claude Desktop configuration for source/development use

---

## 🚀 Quick Setup

### Method 1: Codex from PyPI (Recommended)

```bash
# 1. Install from official PyPI
python -m pip install -U drissionpage-mcp

# 2. Verify the command and environment
drissionpage-mcp --version
drissionpage-mcp doctor

# 3. Add examples/codex-config.toml to ~/.codex/config.toml
#    or to .codex/config.toml in a trusted project.

# 4. Verify Codex can see the server
codex mcp list
```

Expected Codex TOML:

```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

You can also add it with the Codex CLI:

```bash
codex mcp add drissionpage -- drissionpage-mcp
```

### Method 2: Codex from Source (Developers)

```bash
# 1. Clone and install
git clone https://github.com/jumodada/Drissionpage-MCP-Server.git
cd Drissionpage-MCP-Server
python -m pip install -e ".[dev]"
python playground/quick_start.py

# 2. Copy config and edit path
cp examples/codex-source-config.toml temp-codex-config.toml
# Replace <REPLACE_WITH_YOUR_DRISSIONMCP_PATH> with this checkout's absolute path.

# 3. Merge it into ~/.codex/config.toml or trusted project .codex/config.toml

# 4. Verify
codex mcp list
```

### Method 3: JSON MCP Clients from PyPI

```bash
# 1. Install
python -m pip install -U drissionpage-mcp

# 2. Verify the command and environment
drissionpage-mcp --version
drissionpage-mcp doctor

# 3. Copy examples/pypi-install-config.json into your MCP settings JSON
# Do not append raw JSON to an existing file unless you merge it into mcpServers.

# 4. Restart your MCP client
```

### Method 4: JSON MCP Clients from Source

```bash
# 1. Clone and install
git clone https://github.com/jumodada/Drissionpage-MCP-Server.git
cd Drissionpage-MCP-Server
python -m pip install -e ".[dev]"
python playground/quick_start.py

# 2. Copy config and edit path
cp examples/claude-code-config.json temp-config.json
# Edit temp-config.json and replace <REPLACE_WITH_YOUR_DRISSIONMCP_PATH>

# 3. Merge temp-config.json into your MCP settings JSON
# Do not append raw JSON to an existing file unless you merge it into mcpServers.

# 4. Restart your MCP client
```

---

## 🗂️ Configuration File Locations

### Codex CLI / IDE
- **User config**: `~/.codex/config.toml`
- **Project config**: `.codex/config.toml` inside a trusted project
- **TUI check**: run `/mcp`
- **Shell check**: run `codex mcp list`

### Claude Code / JSON MCP Clients
- **Claude Code**: `~/.config/claude-code/mcp_settings.json`
- **Claude Desktop macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Claude Desktop Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Claude Desktop Linux**: `~/.config/Claude/claude_desktop_config.json`

---

## 🔧 Configuration Options

### Codex Basic Configuration

```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

### Codex Advanced Configuration with Environment Variables

```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60

[mcp_servers.drissionpage.env]
CHROME_PATH = "/custom/path/to/chrome"
DP_HEADLESS = "1"
DP_NO_SANDBOX = "1"
```

### JSON Basic Configuration

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

### JSON Advanced Configuration with Environment Variables

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "python",
      "args": ["-m", "drissionpage_mcp.cli", "--log-level", "DEBUG"],
      "cwd": "/path/to/DrissionMCP",
      "env": {
        "CHROME_PATH": "/custom/path/to/chrome",
        "LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

### Options Explanation

- **`command`**: The command to start the MCP server
  - PyPI install: `"drissionpage-mcp"`
  - Source install: `"python"`
- **`args`**: Command line arguments
  - `["-m", "drissionpage_mcp.cli"]` - Run as Python module
  - `["--log-level", "DEBUG"]` - Set logging level
- **`cwd`**: Working directory for source installation
  - Absolute path to your DrissionMCP project directory
- **`env`**: Environment variables
  - Custom browser path, headless mode, sandbox flags, logging configuration, etc.

---

## ✅ Verify Installation

After configuration, test your setup:

```bash
# Codex CLI / IDE
codex mcp list
# In the Codex TUI, run: /mcp

# JSON MCP client prompt example
"Use DrissionPage to navigate to https://example.com and take a screenshot"

# Manual checks
drissionpage-mcp --version
drissionpage-mcp doctor
python playground/quick_start.py
```

If `pip install drissionpage-mcp==0.4.0` cannot find the latest version, your package mirror may be stale. Retry with official PyPI:

```bash
python -m pip install -U --index-url https://pypi.org/simple drissionpage-mcp
```

---

## 🐛 Troubleshooting

### Codex server not appearing?
- Run `codex mcp list` from the same shell.
- In the Codex TUI, run `/mcp`.
- Confirm `~/.codex/config.toml` TOML syntax is valid.
- If using project `.codex/config.toml`, make sure the project is trusted.
- Restart Codex after configuration changes.

### JSON client config not loading?
- Check file path is correct.
- Ensure JSON syntax is valid.
- Restart the MCP client after changes.

### Server not starting?
- Verify Python and dependencies are installed.
- Run `drissionpage-mcp doctor`.
- Check the `cwd` path exists for source installation.
- Try running manually: `python -m drissionpage_mcp.cli --log-level DEBUG`.

### Tools not appearing?
- Ensure server started successfully.
- Check client logs.
- Verify the configuration was added to the right file.

---

## 📚 More Information

- [Main README](../README.md)
- [Compatibility](../docs/compatibility.md)
- [Tool contract](../docs/tool-contract.md)
- [Troubleshooting](../docs/troubleshooting.md)
- [Changelog](../CHANGELOG.md)

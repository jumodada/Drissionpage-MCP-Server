# DrissionPage MCP Server

> Professional browser automation for Codex, Claude Code, and MCP clients powered by DrissionPage

[![PyPI](https://img.shields.io/pypi/v/drissionpage-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/drissionpage-mcp/)
[![Downloads](https://pepy.tech/badge/drissionpage-mcp/month)](https://pepy.tech/project/drissionpage-mcp)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server/branch/main/graph/badge.svg)](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)]()

**Official Repositories**: [GitHub](https://github.com/jumodada/Drissionpage-MCP-Server) | [GitCode](https://gitcode.com/g1879/DrissionMCP)

[English Version](README.md) | [中文版本](README_CN.md)

## 🧭 Client Setup Navigation

- [Install + screenshot walkthrough](#-first-success-path)
- [Codex CLI/IDE quick setup](#-setup-in-codex-cliide-30-seconds)
- [Codex CLI/IDE integration example](#codex-cli--ide)
- [Claude Code setup](#claude-code)
- [Cursor setup](#cursor)
- [Claude Desktop setup](#claude-desktop)
- [Troubleshooting](#-troubleshooting)

---

## 🚀 What is DrissionPage MCP?

**DrissionPage MCP Server** is a local Model Context Protocol (MCP) server that brings DrissionPage browser automation tools to Codex CLI/IDE, Claude Code, Claude Desktop, and other MCP clients.

Unlike screenshot-based approaches, it provides **structured, deterministic web automation** through 21 tools plus MCP Resources/Prompts that leverage the efficiency of [DrissionPage](https://github.com/g1879/DrissionPage), a high-performance browser automation framework.

### 🌟 Why Choose DrissionPage MCP?

- **LLM-Optimized**: Works with structured data instead of requiring vision models
- **Deterministic**: Reliable element selection with CSS/XPath normalization for LLM-friendly selectors
- **Fast & Lightweight**: Built on DrissionPage's efficient engine with minimal overhead
- **Type-Safe**: Full type hints and Pydantic validation for all tools
- **Open-source Friendly**: Includes compatibility notes, troubleshooting, and CI checks for maintainable contributions
- **Easy Integration**: Simple `pip install` + Codex TOML or MCP JSON configuration

---

## ⚡ First Success Path

```bash
# Install from PyPI
python -m pip install -U drissionpage-mcp

# Verify package and environment
drissionpage-mcp --version
drissionpage-mcp doctor
```

Then add the Codex or MCP client configuration below and restart your client.

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/01-install.png" width="700" alt="pip install drissionpage-mcp">
  <br><br>
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/03-doctor.png" width="700" alt="drissionpage-mcp doctor — all checks green">
</p>

---

## 📦 Setup in Codex CLI/IDE (30 seconds)

Codex supports local stdio MCP servers through `config.toml`; the CLI and IDE extension share the same MCP configuration.

1. **Edit Codex configuration**:
   - User-level: `~/.codex/config.toml`
   - Project-level: `.codex/config.toml` inside a trusted project

2. **Add this configuration**:
   ```toml
   [mcp_servers.drissionpage]
   command = "drissionpage-mcp"
   startup_timeout_sec = 20
   tool_timeout_sec = 60
   ```

3. **Restart Codex**. In the TUI, run `/mcp`; from a shell, run `codex mcp list`.

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/06-codex.png" width="700" alt="Codex config.toml">
</p>

For Claude Code, Claude Desktop, and other JSON-based MCP clients, see [Integration Examples](#-integration-examples).

---

## 🎯 Quick Examples

### Navigate and Screenshot
```
"Visit https://example.com and take a screenshot for me"
```

### Search and Extract
```
"Go to Wikipedia, search for Python, and get the first paragraph"
```

### Form Automation
```
"Fill out the form at https://httpbin.org/forms/post and submit it"
```

### Data Scraping
```
"Get the top 10 news headlines from news.ycombinator.com"
```

---

## 🛠️ 21 Powerful Tools + MCP Resources/Prompts

### 🌐 Navigation (4 tools)
- `page_navigate` - Navigate to any URL
- `page_go_back` / `page_go_forward` - Browser history
- `page_refresh` - Reload current page

### 🎯 Element Interaction & Extraction (8 tools)
- `element_find` - Find one element by CSS selector or XPath; bare selectors like `h1` are treated as CSS
- `element_find_all` - Extract bounded repeated elements with text, attributes, and recommended selectors
- `element_click` - Click any element
- `element_type` - Input text into elements
- `element_get_text` - Get element or page text
- `element_get_attribute` - Get an HTML attribute
- `element_get_property` - Get a live DOM property such as an input value
- `element_get_html` - Get element or page HTML

### 📸 Page Operations (6 tools)
- `page_screenshot` - Capture full page or viewport
- `page_snapshot` - Return a bounded page outline with headings, links, buttons, inputs, forms, and selector recommendations
- `page_resize` - Adjust browser window
- `page_click_xy` - Click by coordinates
- `page_close` - Close browser
- `page_get_url` - Get current URL

### ⏱️ Wait Operations (3 tools)
- `wait_for_element` - Wait for element to appear (with timeout)
- `wait_for_url` - Wait until the current URL contains text
- `wait_time` - Delay execution

### 🧩 MCP Resources and Prompts
- Resources: `drissionpage://session/summary`, `drissionpage://page/current`, `drissionpage://tools/catalog`, `drissionpage://policy/summary`
- Prompts: `browser_navigate_and_summarize`, `browser_extract_structured_data`, `browser_fill_form_safely`, `browser_debug_page_issue`

---

## 📚 Documentation

| Guide | Description |
|-------|-------------|
| [README.md](README.md) | Installation, tools, and architecture |
| [docs/compatibility.md](docs/compatibility.md) | Supported Python, DrissionPage, MCP, and browser versions |
| [docs/tool-contract.md](docs/tool-contract.md) | Public MCP tool names, inputs, annotations, and response shape |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Doctor command, browser startup, and client setup fixes |
| [docs/release-checklist.md](docs/release-checklist.md) | Release validation and publishing checklist |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

---

## 🏗️ Architecture

Built with **clean, modular design**:

```
DrissionMCP/
├── drissionpage_mcp/
│   ├── cli.py              # Entry point
│   ├── server.py           # MCP server
│   ├── context.py          # Browser management
│   ├── response.py         # Response formatting
│   ├── tab.py              # Page operations
│   └── tools/              # 21 automation and page-understanding tools
├── tests/                  # Unit tests
└── playground/             # Testing utilities
```

**Key Principles**:
- ✅ Type-safe Pydantic models for all tools
- ✅ Async/await throughout
- ✅ Clean separation of concerns
- ✅ Comprehensive error handling
- ✅ Unit and protocol test coverage for core tool registration/response behavior

---

## 🔧 Configuration

### Codex CLI / IDE (Recommended)
```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60

# Optional browser/runtime environment variables:
# [mcp_servers.drissionpage.env]
# CHROME_PATH = "/custom/path/to/chrome"
# DP_HEADLESS = "1"
# DP_NO_SANDBOX = "1"
```

You can also add it with the Codex CLI:

```bash
codex mcp add drissionpage -- drissionpage-mcp
```

If Codex/Cursor/Claude Desktop is launched from a GUI and cannot see your shell
`PATH` or virtualenv, use the absolute Python executable instead:

```toml
[mcp_servers.drissionpage]
command = "/absolute/path/to/python"
args = ["-m", "drissionpage_mcp.cli"]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

### JSON MCP Clients
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

### Advanced JSON Setup
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp",
      "args": ["--log-level", "DEBUG"],
      "env": {
        "CHROME_PATH": "/custom/path/to/chrome"
      }
    }
  }
}
```

Absolute-Python fallback for GUI clients:

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "drissionpage_mcp.cli"],
      "env": {
        "CHROME_PATH": "/custom/path/to/chrome",
        "DP_HEADLESS": "1",
        "DP_NO_SANDBOX": "1"
      }
    }
  }
}
```

---

## 📋 Requirements

- **Python 3.10+** (3.11+ recommended)
- **Chrome or Chromium** browser
- **Any MCP-compatible client**: Codex CLI/IDE, Claude Code, Claude Desktop, Cursor, VS Code, etc.

---

## 🧪 Testing

### Verify Installation
```bash
# Environment diagnostics; add --launch-browser for a browser startup check
drissionpage-mcp doctor
drissionpage-mcp doctor --launch-browser

# Source checkout tests
python -m pip install -e ".[dev]"
python -m pytest tests/

# Coverage report (CI enforces the current 95% floor and uploads coverage.xml)
python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml
```

GitHub Actions runs lint, unit, protocol, package, browser integration, and
coverage jobs. Codecov is configured through `codecov.yml` and the CI workflow;
set the `CODECOV_TOKEN` repository secret so the upload step can publish
`coverage.xml` reliably from GitHub Actions.

### Try It Out
```bash
# Interactive testing
python playground/local_test.py

# Quick start validation
python playground/quick_start.py
```

---

## 🚀 Use Cases

✅ **Automated Testing** - Test web applications
✅ **Data Scraping** - Extract structured data from websites
✅ **Form Automation** - Fill and submit forms
✅ **Monitoring** - Check for updates or changes
✅ **Screenshot Verification** - Capture and verify page state
✅ **Content Analysis** - Analyze web content programmatically

---

## 🐛 Troubleshooting

### Tools Not Loading?
```bash
drissionpage-mcp --version
```
Should output the installed package version, for example `drissionpage-mcp 0.4.10`.

### Browser Issues?
```bash
# Check browser installation
which google-chrome    # Linux
which chromium         # macOS
```

### Codex / MCP Client Not Finding Server?
- Codex: run `codex mcp list`; in the TUI, run `/mcp`
- JSON clients: verify config file path and JSON syntax
- Restart Codex or your MCP client after changes
- Check logs: `drissionpage-mcp --log-level DEBUG`

See [docs/troubleshooting.md](docs/troubleshooting.md) for the complete troubleshooting guide.

---

## 📊 Project Status

| Component | Status |
|-----------|--------|
| **Core Features** | ✅ Complete |
| **Testing** | ✅ Unit/protocol checks, optional browser smoke |
| **Documentation** | ✅ Setup, compatibility, troubleshooting, release checklist |
| **Package** | ✅ PyPI metadata and build checks |
| **Status** | 🟡 Beta; real browser behavior depends on local Chrome/Chromium and target sites |

**Version**: 0.4.10 | **License**: Apache 2.0 | **Maintained**: ✅ Active

---

## 🗺️ Roadmap

### Current (v0.4.10)
- [x] 21 core automation and page-understanding tools with removed alias surface
- [x] stdio MCP server integration
- [x] Doctor diagnostics for local setup
- [x] Stable JSON mirror, `structuredContent`, and typed per-tool MCP `outputSchema`
- [x] Structured recovery hints in `error.details.hints` for common failures
- [x] Balanced `page_snapshot` output so link-heavy pages still expose controls and forms
- [x] Opt-in local safety policy for navigation and screenshot paths
- [x] Resources, prompts, eval harness, compatibility, and troubleshooting documentation
- [x] PyPI distribution

### Future (v0.5+)
- [ ] Form handling utilities
- [ ] File upload support
- [ ] Shadow DOM selectors
- [ ] Session persistence
- [ ] Proxy support
- [ ] Network interception

---

## 📖 Integration Examples

### Codex CLI / IDE
```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

Verify with:

```bash
codex mcp list
```

### Claude Code
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

Config file: `~/.config/claude-code/mcp_settings.json` (macOS/Linux) or
`%APPDATA%\claude-code\mcp_settings.json` (Windows).

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/04-claude-code.png" width="700" alt="Claude Code mcp_settings.json">
</p>

### Cursor
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

Config file: `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project). You
can also add it from **Cursor Settings → Tools & MCPs → New MCP Server**.

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/05-cursor.png" width="700" alt="Cursor mcp.json">
  <br><br>
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/08-cursor-ui.png" width="540" alt="Cursor Settings — add a new MCP server">
</p>

### Claude Desktop
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

Once connected, the tools load automatically:

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/07-connected.png" width="700" alt="MCP client with DrissionPage tools loaded">
</p>

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Make focused changes
4. Run the relevant checks
5. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, validation, and compatibility expectations.

---

## 🔒 Security

- Runs locally in your environment
- Uses a local browser that may have access to authenticated sessions, cookies, downloads, and page content
- Can open and interact with any site reachable from the local machine
- Does not require external API credentials

**Best Practices**:
- Use a dedicated browser profile for sensitive workflows
- Review MCP client prompts before allowing actions on authenticated or production systems
- Respect website terms of service, robots.txt, and rate limits
- See [SECURITY.md](SECURITY.md) for reporting and safe-usage guidance

---

## 📄 License

Licensed under **Apache License 2.0** - see [LICENSE](LICENSE)

---

## 📈 Statistics

[![Downloads](https://pepy.tech/badge/drissionpage-mcp)](https://pepy.tech/project/drissionpage-mcp)
[![PyPI Version](https://img.shields.io/pypi/v/drissionpage-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/drissionpage-mcp/)

---

## 🌟 Show Your Support

If you find this project useful, please consider:
- ⭐ Starring on [GitHub](https://github.com/jumodada/Drissionpage-MCP-Server)
- 📤 Sharing with your network
- 💬 Leaving feedback or suggestions
- 🐛 Reporting issues to help improve

---

**Made with ❤️ by [Wukunyun](https://github.com/jumodada)**

**Ready to automate your workflows?** Install now: `python -m pip install -U drissionpage-mcp`

---

## 🆕 Latest Version: v0.4.10

Released on 2026-06-29. This release improves real MCP recovery behavior without adding new browser actions:

- Failure payloads now include machine-readable `error.details.hints` for common recovery paths.
- Missing element and selector failures suggest `page_snapshot`, `element_find_all`, `wait_for_element`, and iframe/dynamic-content checks.
- `page_snapshot` now keeps inputs, buttons, and forms visible on link-heavy pages while respecting the total `max_elements` cap.
- Timeout, browser startup, screenshot, navigation, policy, invalid-argument, and unknown-tool failures now include targeted next steps.
- `MCP_ARGUMENT_INVALID` still protects strict schemas and now points clients toward exact snake_case field names.
- Browser startup hints point to `drissionpage-mcp doctor --launch-browser`, `CHROME_PATH`, `DP_HEADLESS`, and `DP_NO_SANDBOX`.
- The top-level JSON_RESULT envelope, 21-tool registry, strict input schemas, and typed `outputSchema` contracts remain unchanged.

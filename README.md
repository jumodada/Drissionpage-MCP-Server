# DrissionPage MCP Server

> Professional browser automation for Codex, Claude Code, and MCP clients powered by DrissionPage

[![PyPI](https://img.shields.io/pypi/v/drissionpage-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/drissionpage-mcp/)
[![Downloads](https://pepy.tech/badge/drissionpage-mcp/month)](https://pepy.tech/project/drissionpage-mcp)

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/vision-natural-pointer-demo.gif" width="662" alt="AI vision-directed natural pointer interaction demo">
  <br>
  <sub><strong>A new interaction layer for multimodal AI</strong> — vision coordinates in, natural pointer action chains out.</sub>
</p>

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server/branch/main/graph/badge.svg)](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)]()

**Official Repositories**: [GitHub](https://github.com/jumodada/Drissionpage-MCP-Server) | [GitCode](https://gitcode.com/g1879/DrissionMCP)

[English Version](README.md) | [中文版本](README_CN.md)

## 🖱️ Vision-Guided Human–Computer Interaction

**DrissionPage MCP 0.5.8 adds a major new interaction layer for multimodal AI:** it can turn a vision model's viewport coordinate into a complete, physically plausible pointer action chain—not just a raw teleport-and-click.

> **One MCP call connects visual understanding to real browser interaction.** The model identifies where to act; DrissionPage MCP handles how the pointer gets there and performs the click.

```text
Screenshot / page observation
        ↓
Multimodal model identifies viewport coordinates
        ↓
page_click_xy(profile="natural")
        ↓
Cubic Bézier motion → reaction pause → press → hold → release
        ↓
Observe and verify the resulting page state
```

### What makes this interaction layer different?

- **Natural pointer dynamics**: 20–35 cubic Bézier movement steps instead of coordinate teleportation.
- **Human-like timing**: 8–25ms point intervals, smoothstep ease-in-out, and a 100–300ms reaction pause after arrival.
- **Physical click semantics**: 50–120ms press duration with correct Chromium CDP button state for left, right, and middle clicks.
- **Controlled micro-motion**: bounded ±0.5 CSS-pixel intermediate jitter while the final point remains exact.
- **Failure-safe execution**: a pressed button is always released if the action chain is interrupted.
- **Model-readable evidence**: results include the chosen profile, start and target coordinates, step count, reaction delay, hold duration, and planned duration.

This makes vision-guided operation practical for canvas controls, visual editors, maps, charts, non-semantic widgets, responsive interfaces, and other surfaces where selectors or accessibility metadata are incomplete. Structured DOM automation remains the preferred path when reliable selectors are available; the vision interaction layer expands what an MCP agent can operate when they are not.

```json
{
  "x": 442,
  "y": 369,
  "start_x": 100,
  "start_y": 100,
  "profile": "natural",
  "button": "left",
  "element": "visually identified control"
}
```

Designed for legitimate UI automation, testing, accessibility workflows, and technical research. Security or anti-automation challenge completion is not offered as a guaranteed supported capability.

## 🧭 Client Setup Navigation

- [Vision-guided human–computer interaction](#vision-guided-humancomputer-interaction)
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

Structured, deterministic automation remains the default through 52 tools plus MCP Resources/Prompts. When selectors or accessibility metadata are insufficient, 0.5.8 also provides an optional **vision-guided human–computer interaction layer** that converts viewport coordinates into natural Chromium pointer action chains, powered by [DrissionPage](https://github.com/g1879/DrissionPage).

### 🌟 Why Choose DrissionPage MCP?

- **Structured-First, Vision-Ready**: Uses DOM structure when available and multimodal coordinates when visual interaction is the better tool
- **Deterministic**: Reliable element selection with CSS/XPath normalization for LLM-friendly selectors
- **Vision-Ready Interaction**: Converts multimodal model coordinates into natural pointer movement and physically timed clicks
- **Fast & Lightweight**: Built on DrissionPage's efficient engine with minimal overhead
- **Type-Safe**: Full type hints and Pydantic validation for all tools
- **Open-source Friendly**: Includes compatibility notes, troubleshooting, and CI checks for maintainable contributions
- **Easy Integration**: Simple `pip install` + Codex TOML or MCP JSON configuration

### ✅ Quality and Real-World Validation

DrissionPage MCP is backed by a strict regression suite and browser-backed scenario checks:

- **Strict automated tests**: unit, protocol, schema snapshot, response-contract, resource/prompt, release-metadata, security-policy, browser-integration, and coverage checks run in CI.
- **95% coverage floor**: CI enforces the current 95% coverage threshold and uploads coverage reports.
- **Real browser verification**: Chrome/Chromium-backed integration tests exercise the same MCP tools exposed to clients.
- **Scenario validation**: the playground MCP Lab covers realistic forms, commerce pages, social feeds, timelines, dynamic waits, iframe cases, and recovery paths without depending on public demo websites.

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

## 🛠️ 46 Powerful Tools + MCP Resources/Prompts

### 🌐 Navigation (4 tools)
- `page_navigate` - Navigate to any URL; optionally open it in a new tab with `new_tab` or return an `observe` change summary
- `page_go_back` / `page_go_forward` - Browser history
- `page_refresh` - Reload current page

### 🗂️ Tab Operations (3 tools)
- `tab_list` - List open browser tabs with stable MCP tab IDs
- `tab_switch` - Switch to a tab returned by `tab_list`
- `tab_close` - Close one tab without closing the whole browser

### 🎯 Element Interaction & Extraction (13 tools)
- `element_find` - Find one element by CSS selector or XPath; bare selectors like `h1` are treated as CSS
- `element_find_all` - Extract bounded repeated elements with text, attributes, and recommended selectors
- `element_click` - Click any element
- `element_type` - Input text into elements
- `element_upload_file` - Upload files from `DP_MCP_UPLOAD_ROOT` to `input[type=file]`
- `element_scroll_into_view` - Bring an element into the viewport before acting
- `element_hover` - Hover an element to trigger menu/tooltip states
- `element_select` - Select an option by value, text, or index
- `element_check` - Check or uncheck checkbox/radio controls
- `element_get_text` - Get element or page text
- `element_get_attribute` - Get an HTML attribute
- `element_get_property` - Get a live DOM property such as an input value
- `element_get_html` - Get element or page HTML

### 🧾 Form Operations (1 tool)
- `form_inspect` - Inspect forms and controls with labels, selectors, requirements, options, and safe optional values

### 📸 Page Operations (11 tools)
- `page_screenshot` - Capture an inline full-page or viewport screenshot
- `page_screenshot_save` - Save a screenshot under `DP_MCP_SCREENSHOT_ROOT`
- `page_snapshot` - Return a bounded page outline with headings, links, buttons, inputs, forms, and selector recommendations
- `page_observe` - Return a compact page fingerprint with URL, title, counts, visible text samples, active element, and recent console summary
- `page_evaluate` - Run bounded JavaScript in the current page and return a JSON-safe result
- `page_scroll` - Scroll the page by direction or to a position
- `keyboard_press` - Send keys to the active element/page
- `page_resize` - Adjust browser window
- `page_click_xy` - Click by coordinates
- `page_close` - Close browser
- `page_get_url` - Get current URL

### 🧱 Frame / Shadow DOM (5 tools)
- `frame_list` - List iframe/frame contexts without changing global frame state
- `frame_snapshot` - Inspect a selected iframe with bounded outline data
- `frame_find` - Find an element inside a selected iframe
- `shadow_find` - Find one element inside an open shadow root
- `shadow_find_all` - Extract repeated elements inside an open shadow root

### 🍪 Cookies & Storage (4 tools)
- `browser_cookies_get` - Read normalized cookies with values redacted by default
- `storage_get` - Read localStorage/sessionStorage by key or as a map
- `storage_set` - Set one localStorage/sessionStorage item without echoing the value
- `storage_clear` - Clear one storage key or an entire storage area

### 🧪 Debug / Observability (1 tool)
- `page_console_logs` - Read bounded browser console messages with level filtering, cursor pagination, and limits

### ⏱️ Wait Operations (4 tools)
- `wait_for_element` - Wait for element to appear (with timeout)
- `wait_for_url` - Wait until the current URL contains text
- `wait_until` - Wait for observable conditions such as clickable, hidden, stable, text, or URL matches
- `wait_time` - Delay execution

### 🧩 MCP Resources and Prompts
- Resources: `drissionpage://session/summary`, `drissionpage://session/history`, `drissionpage://session/state`, `drissionpage://session/config`, `drissionpage://guide/model-usage`, `drissionpage://page/current`, `drissionpage://tools/catalog`, `drissionpage://policy/summary`
- Prompts: `drissionpage_mcp_usage_playbook`, `browser_navigate_and_summarize`, `browser_extract_structured_data`, `browser_fill_form_safely`, `browser_debug_page_issue`

---

## 📚 Documentation

| Guide | Description |
|-------|-------------|
| [README.md](README.md) | Installation, tools, and architecture |
| [docs/compatibility.md](docs/compatibility.md) | Supported Python, DrissionPage, MCP, and browser versions |
| [docs/tool-contract.md](docs/tool-contract.md) | Public MCP tool names, inputs, annotations, and response shape |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Doctor command, browser startup, and client setup fixes |
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
│   └── tools/              # 46 automation, tab/frame/shadow, page-understanding, form, debug, and session-state tools
├── tests/                  # Unit tests
└── playground/             # MCP Lab business-scenario playground
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
        "DP_HEADLESS": "1"
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

# Browser-backed MCP Lab scenario checks
DP_HEADLESS=1 python playground/run_mcp_lab.py --all --json
```

GitHub Actions runs lint, unit, protocol, package, browser integration, and
coverage jobs. Codecov is configured through `codecov.yml` and the CI workflow.

### Try It Out
```bash
# No-browser MCP registry check
python playground/run_mcp_lab.py --case registry

# Local deterministic site check
python playground/run_mcp_lab.py --case site

# Browser-backed form inspection scenario
DP_HEADLESS=1 python playground/run_mcp_lab.py --case form-inspect
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
Should output the installed package version, for example `drissionpage-mcp 0.5.8`.

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
| **Testing** | ✅ Strict unit/protocol/schema checks plus browser-backed scenarios |
| **Documentation** | ✅ Setup, compatibility, troubleshooting, and public tool contracts |
| **Package** | ✅ PyPI metadata and build checks |
| **Status** | 🟡 Beta; real browser behavior depends on local Chrome/Chromium and target sites |

**Version**: 0.5.8 | **License**: Apache 2.0 | **Maintained**: ✅ Active

---

## 🗺️ Roadmap

### Current (v0.5.8)
- [x] 52 core automation, tab/frame/shadow, page-understanding, form-inspection, workflow, network-listener, session-state, and console-observability tools with removed alias surface
- [x] stdio MCP server integration
- [x] Doctor diagnostics for local setup
- [x] Stable JSON mirror, `structuredContent`, and typed per-tool MCP `outputSchema`
- [x] Structured recovery hints in `error.details.hints` for common failures
- [x] Balanced `page_snapshot` output so link-heavy pages still expose controls and forms
- [x] `form_inspect` read-only form inventory with labels, selectors, requirements, options, and safe optional values
- [x] Tab management with `tab_list`, `tab_switch`, `tab_close`, and `page_navigate(new_tab=true)`
- [x] Observable actions with `page_observe`, `page_evaluate`, `wait_until`, and optional `observe=true` changes on navigation, click, and type
- [x] Console observability with `page_console_logs`, console summary in `page_observe`, and console change fields in `observe=true`
- [x] Workflow helpers with `browser_open_and_snapshot`, `browser_extract_links`, and `form_fill_preview`
- [x] Network listener beta with `network_listen_start`, `network_listen_wait`, and `network_listen_stop` for HTTP/XHR/Fetch observation
- [x] Natural `page_click_xy` pointer action chains with cubic Bézier motion, smoothstep easing, bounded jitter, reaction delay, and realistic button hold time
- [x] File upload, scrolling, hover, select/check, keyboard, iframe, shadow DOM, cookie, and storage tools for DrissionPage 4.x
- [x] Chrome sandbox remains enabled by default; `DP_NO_SANDBOX=1` is reserved for restricted container/root environments
- [x] Redacted session history resource and response size metadata for bounded outputs
- [x] Opt-in local safety policy for navigation and screenshot paths
- [x] Resources, prompts, eval harness, compatibility, and troubleshooting documentation
- [x] PyPI distribution

### Future (v0.6+)
- [ ] Promote workflow/network beta contracts toward 0.6.0 after field testing
- [ ] Optional session persistence beyond redacted state summaries
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

## 🆕 Latest Version: v0.5.8

Released on 2026-07-10. This release upgrades the existing `page_click_xy` tool for vision-directed UI operation while preserving the 52-tool surface and DrissionPage 4.x support:

- `page_click_xy` now defaults to the `natural` pointer profile: 20–35 cubic Bézier movement steps, 8–25 ms point intervals, ±0.5 CSS-pixel intermediate jitter, and exact target arrival.
- Natural motion samples the path with `t*t*(3-2*t)` smoothstep ease-in-out, pauses 100–300 ms after arrival, then holds the selected mouse button for 50–120 ms before release.
- `natural`, `precise`, and `direct` profiles share one pointer capability; an explicit start coordinate pair is available without adding compatibility wrappers or another public tool.
- Pointer execution uses Chromium CDP move/press/release events, synchronizes DrissionPage cursor state, and releases a held button during failure cleanup.
- Model-facing guidance is now workflow-first: use `browser_open_and_snapshot` for fresh navigate-and-inspect tasks, `browser_extract_links` for bounded link discovery, and `page_navigate` only for navigation-only retries.
- MCP prompts such as `drissionpage_mcp_usage_playbook`, structured extraction, safe form filling, and page debugging now steer clients through workflow helpers and bounded `page_snapshot` / `page_observe` checks before lower-level primitives.
- `drissionpage://guide/model-usage` exposes `workflow_routes` so agents can choose summarize/inspect, link discovery, safe form fill, and network observation sequences without guessing.
- `drissionpage://tools/catalog` now includes descriptions alongside annotations and output data schema names, improving AI tool choice while preserving the existing catalog contract.
- Recovery hints are more actionable: fresh sessions point to `browser_open_and_snapshot`, `MCP_ARGUMENT_INVALID` points to schema/catalog inspection, and unknown tools point to `drissionpage://guide/model-usage`.
- The 0.5.6 helpers remain the stable foundation: `browser_open_and_snapshot`, `browser_extract_links`, `form_fill_preview`, `network_listen_start`, `network_listen_wait`, and `drissionpage://session/config` are unchanged.
- Existing page-understanding, observable-action, console, tab, form, upload, iframe/shadow, cookie/storage, and recovery-hint tools remain compatible; observable changes still include `console_errors_added`; bounded outputs keep `meta.approx_tokens`.
- `drissionpage-mcp doctor` still flags DrissionPage 5.x as unsupported and `drissionpage-mcp doctor --launch-browser` remains the browser startup check; Chrome sandbox remains enabled by default and `DP_NO_SANDBOX=1` is reserved for restricted container/root environments.
- The top-level JSON_RESULT envelope, strict validation, `structuredContent`, and typed `outputSchema` contracts remain in place; `page_click_xy` now returns typed motion metadata and the public registry stays at 52 tools.

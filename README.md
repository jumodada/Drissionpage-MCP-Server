# DrissionPage MCP Server

> Professional browser automation for Claude Code and MCP clients powered by DrissionPage

[![PyPI](https://img.shields.io/pypi/v/drissionpage-mcp.svg)](https://pypi.org/project/drissionpage-mcp/)
[![Downloads](https://pepy.tech/badge/drissionpage-mcp/month)](https://pepy.tech/project/drissionpage-mcp)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server/branch/main/graph/badge.svg)](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)]()

**Official Repositories**: [GitHub](https://github.com/jumodada/Drissionpage-MCP-Server) | [GitCode](https://gitcode.com/g1879/DrissionMCP)

[English Version](README.md) | [中文版本](README_CN.md)

---

## 🚀 What is DrissionPage MCP?

**DrissionPage MCP Server** is a local Model Context Protocol (MCP) server that brings DrissionPage browser automation tools to Claude Code, Claude Desktop, and other MCP clients.

Unlike screenshot-based approaches, it provides **structured, deterministic web automation** through 21 powerful tools that leverage the efficiency of [DrissionPage](https://github.com/g1879/DrissionPage), a high-performance browser automation framework.

### 🌟 Why Choose DrissionPage MCP?

- **LLM-Optimized**: Works with structured data instead of requiring vision models
- **Deterministic**: Reliable element selection with CSS and XPath support
- **Fast & Lightweight**: Built on DrissionPage's efficient engine with minimal overhead
- **Type-Safe**: Full type hints and Pydantic validation for all tools
- **Open-source Friendly**: Includes compatibility notes, troubleshooting, and CI checks for maintainable contributions
- **Easy Integration**: Simple `pip install` + JSON configuration

---

## ⚡ First Success Path

```bash
# Install from PyPI
python -m pip install -U drissionpage-mcp

# Verify package and environment
drissionpage-mcp --version
drissionpage-mcp doctor
```

Then add the MCP client configuration below and restart your client.

---

## 📦 Setup in Claude Code (30 seconds)

1. **Edit MCP configuration**:
   - macOS/Linux: `~/.config/claude-code/mcp_settings.json`
   - Windows: `%APPDATA%\claude-code\mcp_settings.json`

2. **Add this configuration**:
   ```json
   {
     "mcpServers": {
       "drissionpage": {
         "command": "drissionpage-mcp"
       }
     }
   }
   ```

3. **Restart Claude Code** and start using!

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

## 🛠️ 21 Powerful Tools

### 🌐 Navigation (4 tools)
- `page_navigate` - Navigate to any URL
- `page_go_back` / `page_go_forward` - Browser history
- `page_refresh` - Reload current page

### 🎯 Element Interaction & Extraction (8 tools)
- `element_find` - Find elements by CSS selector or XPath
- `element_click` - Click any element
- `element_type` / `element_input_text` - Input text into elements
- `element_get_text` - Get element or page text
- `element_get_attribute` - Get an HTML attribute
- `element_get_property` - Get a live DOM property such as an input value
- `element_get_html` - Get element or page HTML

### 📸 Page Operations (5 tools)
- `page_screenshot` - Capture full page or viewport
- `page_resize` - Adjust browser window
- `page_click_xy` - Click by coordinates
- `page_close` - Close browser
- `page_get_url` - Get current URL

### ⏱️ Wait Operations (4 tools)
- `wait_for_element` - Wait for element to appear (with timeout)
- `wait_for_url` - Wait until the current URL contains text
- `wait_time` / `wait_sleep` - Delay execution

---

## 📚 Documentation

| Guide | Description |
|-------|-------------|
| [README.md](README.md) | Installation, tools, and architecture |
| [docs/compatibility.md](docs/compatibility.md) | Supported Python, DrissionPage, MCP, and browser versions |
| [docs/tool-contract.md](docs/tool-contract.md) | Public MCP tool names, inputs, annotations, and response shape |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Doctor command, browser startup, and client setup fixes |
| [docs/release-checklist.md](docs/release-checklist.md) | Release validation and publishing checklist |
| [examples/README.md](examples/README.md) | MCP client configuration examples |
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
│   └── tools/              # 21 automation tools
├── examples/               # Configuration templates
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

### Basic Setup (Recommended)
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

### Advanced Setup
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

See [examples/README.md](examples/README.md) for more configuration options.

---

## 📋 Requirements

- **Python 3.10+** (3.11+ recommended)
- **Chrome or Chromium** browser
- **Any MCP-compatible client**: Claude Code, Claude Desktop, Cursor, VS Code, etc.

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

# Coverage report (CI enforces the current 60% floor and uploads coverage.xml)
python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml
```

GitHub Actions runs lint, unit, protocol, package, browser integration, and
coverage jobs. Codecov is configured through `codecov.yml` and the CI workflow;
public repositories can use the configured OIDC upload, while private mirrors may
need Codecov enabled for the repository first.

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
Should output the installed package version, for example `drissionpage-mcp 0.3.0`.

### Browser Issues?
```bash
# Check browser installation
which google-chrome    # Linux
which chromium         # macOS
```

### Claude Code Not Finding Server?
- Verify config file path
- Restart Claude Code after changes
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

**Version**: 0.3.0 | **License**: Apache 2.0 | **Maintained**: ✅ Active

---

## 🗺️ Roadmap

### Current (v0.3.0)
- [x] 21 core automation tools
- [x] stdio MCP server integration
- [x] Doctor diagnostics for local setup
- [x] Compatibility and troubleshooting documentation
- [x] PyPI distribution

### Future (v0.2+)
- [ ] Form handling utilities
- [ ] File upload support
- [ ] Shadow DOM selectors
- [ ] Session persistence
- [ ] Proxy support
- [ ] Network interception

---

## 📖 Integration Examples

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

See [examples/](examples/) for more client configurations.

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

## 🙏 Acknowledgments

- **[DrissionPage](https://github.com/g1879/DrissionPage)** - Excellent browser automation library
- **[Model Context Protocol](https://modelcontextprotocol.io/)** - Protocol specification
- **[Claude](https://claude.ai)** - Making AI assistants capable and useful

---

## 💬 Support

- 📖 **[Troubleshooting](docs/troubleshooting.md)**
- 🐛 **[Report Issues](https://github.com/jumodada/Drissionpage-MCP-Server/issues)**
- 💡 **[Feature Requests](https://github.com/jumodada/Drissionpage-MCP-Server/discussions)**
- 🔗 **[GitHub Repository](https://github.com/jumodada/Drissionpage-MCP-Server)**
- 📦 **[PyPI Package](https://pypi.org/project/drissionpage-mcp/)**

---

## 📈 Statistics

[![Downloads](https://pepy.tech/badge/drissionpage-mcp)](https://pepy.tech/project/drissionpage-mcp)
[![PyPI Version](https://badge.fury.io/py/drissionpage-mcp.svg)](https://pypi.org/project/drissionpage-mcp/)

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

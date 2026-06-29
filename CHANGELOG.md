# Changelog

All notable changes to the DrissionPage MCP Server project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Tool input schemas now reject unknown fields instead of silently ignoring MCP client or LLM argument typos.
- README and troubleshooting docs now include absolute-Python MCP configuration fallbacks for GUI clients and headless browser guidance for remote/container environments.
- Playground setup guidance now points to maintained README/tool-contract configuration snippets.

### Fixed
- Removed stale coverage, security, and Codecov documentation references left from earlier releases.

## [0.4.1] - 2026-06-26

### Added
- Added selector normalization metadata (`selector`, `locator`, `selector_strategy`, and `selector_normalized`) to element and wait tool responses.
- Added real-browser selector regression coverage for LLM-friendly bare CSS selectors, explicit DrissionPage locators, and CSS attribute selectors.

### Changed
- Bare MCP selectors are now normalized as CSS before calling DrissionPage (`h1` -> `css:h1`, `input[name=q]` -> `css:input[name=q]`); use `text:...` for text matching.
- `element_get_property` now uses the LLM-friendly public input field `property` instead of `property_name`.
- `element_find` now defaults to a 3-second timeout for faster failed-selector feedback while explicit wait tools keep longer defaults.
- Browser-backed CI jobs now require Chrome/Chromium after installation instead of silently skipping browser integration failures.
- Documented Codex CLI/IDE MCP setup with `config.toml` examples and Codex verification commands.

### Fixed
- Fixed MCP `serverInfo.version` so clients see the `drissionpage-mcp` package version instead of the installed MCP SDK version.
- Fixed selector behavior where bare `h1` could match text inside `<style>` and bare CSS attribute selectors such as `input[name=q]` could fail.

## [0.4.0] - 2026-06-26

### Added
- MCP Resources for `drissionpage://session/summary`, `drissionpage://page/current`, `drissionpage://tools/catalog`, and `drissionpage://policy/summary`.
- MCP Prompts for navigation summaries, structured extraction, safe form filling, and page debugging.
- Typed per-tool MCP `outputSchema` data contracts for all 19 public tools.
- Deterministic pytest eval harness under `tests/evals/`.

### Changed
- Tool success responses now put primary machine-readable values in `structuredContent.data` instead of relying on result text.
- Documentation now describes the 0.4.0 resource, prompt, typed-output, and eval contracts.

### Removed
- Removed the 0.3.x public tool aliases `element_input_text` and `wait_sleep`; use `element_type` and `wait_time`.
- Removed internal compatibility facades used by older tests in favor of direct tool definitions.

## [0.3.2] - 2026-06-25

### Added
- Shared MCP `outputSchema` envelope for tools when supported by the installed MCP Python SDK.
- Opt-in local safety policy for navigation allowlists/blocklists, private-network blocking, and screenshot save-root restrictions.
- Release/documentation checks for version drift, Codecov upload configuration, and package-content expectations.

### Changed
- Navigation, history, refresh, click, and typing paths now prefer DrissionPage-native load stabilization with bounded async fallback sleeps.
- README and release docs now describe the current 0.3.2 package state and compatibility-alias policy.

### Security
- Disallowed navigation is rejected before browser initialization when safety policy variables are configured.
- Runtime request throttling remains deferred for the local stdio server; users should respect target-site rate limits and revisit throttling before adding remote transport.

## [0.3.1] - 2026-06-24

### Added
- CI coverage upload to Codecov with README badges and a local 75% coverage floor.
- CI wheel-content check to prevent broad top-level packages from leaking into release artifacts.

### Removed
- Removed the legacy top-level `src` compatibility shim package from source and release artifacts.

### Fixed
- `element_type` now stops immediately when its element wait fails instead of continuing to input.
- Release wheels now expose only the canonical `drissionpage_mcp` top-level package.

## [0.3.0] - 2026-06-24

### Added
- Stable MCP tool response contract with `### JSON_RESULT` text fallback and native `structuredContent`.
- Machine-readable tool error payloads and stable error codes exported from `drissionpage_mcp.errors`.
- `drissionpage-mcp doctor` / `self-test` diagnostics, including optional browser launch verification.
- Deterministic local HTTP fixture, MCP protocol tests, schema snapshot tests, response contract tests, doctor tests, browser integration tests, and CI workflow structure tests.
- GitHub CI jobs for lint, unit, protocol, package, and browser integration checks.
- Open-source governance docs: contributing guide, security policy, compatibility policy, troubleshooting, tool contract, release checklist, and issue/PR templates.
- DrissionPage 4.2 beta compatibility using the `Chromium` browser API instead of relying on deprecated `ChromiumPage`.
- Extraction tools: `element_get_text`, `element_get_attribute`, `element_get_property`, and `element_get_html`.
- Backward-compatible aliases: `element_input_text` and `wait_sleep`; URL wait tool `wait_for_url`.

### Changed
- Python support is now documented and packaged as Python `>=3.10`, matching the MCP SDK dependency floor.
- `page_screenshot` now returns MCP image content plus structured JSON metadata including MIME type, inline/path mode, `full_page`, byte size, width, and height.
- README and example configuration docs now emphasize a practical first-success path and verifiable MCP client setup.

### Fixed
- Correct package import path from the generic `src` package to `drissionpage_mcp`, with old `src` shims retained for source checkouts.
- MCP tool annotations now expose read-only/destructive/idempotent hints.
- Screenshot responses no longer leak temporary files.
- Response rendering is idempotent when `get_content()` is called more than once.
- Browser startup no longer disables web security by default.

### Planned
- Form handling utilities
- File upload support
- Advanced selectors (shadow DOM, iframes)
- Session management
- Proxy support
- Network interception

## [0.1.0] - 2024-01-22

### Added
- Initial release of DrissionPage MCP Server
- 14 browser automation tools:
  - Navigation tools (4): navigate, go_back, go_forward, refresh
  - Element interaction tools (3): find, click, type
  - Page action tools (5): screenshot, resize, click_xy, close, get_url
  - Wait operation tools (2): wait_for_element, wait_time
- Full MCP (Model Context Protocol) integration
- Type-safe tool definitions using Pydantic
- Comprehensive documentation:
  - Quick Start Guide
  - Testing and Integration Guide
  - Publishing Guide
  - Configuration Examples
- Local testing utilities (playground/)
- Unit test suite
- Professional project structure

### Fixed
- Fixed missing method implementations in tab.py:
  - Added `find_element()` method
  - Added `type_text()` method
  - Updated `click_element()` to support timeout parameter
- Fixed missing `wait()` method in context.py
- Fixed syntax errors in playground/local_test.py
- Fixed import path issues in test and example files
- Updated MCP SDK integration for compatibility with latest version

### Changed
- Reorganized configuration examples into examples/ directory
- Updated README.md for professional presentation
- Enhanced pyproject.toml with comprehensive metadata
- Improved error handling throughout the codebase
- Optimized DrissionPage 4.x API usage

### Documentation
- Created comprehensive README.md
- Added QUICKSTART.md for 5-minute setup
- Added TESTING_AND_INTEGRATION.md for detailed usage
- Added PUBLISHING.md for maintainers
- Added examples/README.md for configuration guidance
- Created REFACTORING_SUMMARY.md documenting all changes

## [0.0.1] - 2024-01-08

### Added
- Initial project scaffold
- Basic MCP server structure
- DrissionPage integration framework
- Tool definition system

---

**Legend**:
- `Added` for new features
- `Changed` for changes in existing functionality
- `Deprecated` for soon-to-be removed features
- `Removed` for now removed features
- `Fixed` for any bug fixes
- `Security` in case of vulnerabilities

[Unreleased]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.2.0...v0.3.0
[0.1.0]: https://github.com/jumodada/Drissionpage-MCP-Server/releases/tag/v0.1.0
[0.0.1]: https://github.com/jumodada/Drissionpage-MCP-Server/releases/tag/v0.0.1

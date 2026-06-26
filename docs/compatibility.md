# Compatibility Policy

DrissionPage MCP follows a conservative compatibility policy for Python, DrissionPage, MCP clients, and browser runtime support.

## Supported Versions

| Component | Supported range | Notes |
| --- | --- | --- |
| Python | `>=3.10` | Python 3.11+ is recommended for new installs. |
| DrissionPage | `>=4.1.1.4,<5` | The package includes compatibility helpers for DrissionPage 4.1 and 4.2 browser/tab APIs. |
| MCP Python SDK | `>=1.0.0` dependency; CI currently tests the resolver-selected SDK on Python 3.10-3.12 | The server uses stdio transport for local MCP clients. This repository does not claim every future MCP SDK release until CI covers it. |
| Browser | Chrome or Chromium | A locally installed browser is required for real browser automation. |
| Operating systems | macOS, Linux, Windows | Browser installation paths and MCP client config paths vary by OS. |

## Stability Expectations

- Tool names are treated as public API. `0.4.0` is a documented breaking
  cleanup release that removes the two 0.3.x alias names listed below; future
  removals must be documented in release notes and migration guidance.
- Input schema changes should be backward compatible when possible.
- Tool responses are text/image MCP content blocks. Human-readable wording may change, but success and error responses should remain explicit.
- Browser behavior can vary by Chrome/Chromium version, site content, extensions, and local security settings.

## 0.3.x to 0.4.0 Migration

| Removed 0.3.x tool | 0.4.0 replacement | Notes |
| --- | --- | --- |
| `element_input_text` | `element_type` | Same input fields: `selector`, `text`, optional `timeout`, `clear`. |
| `wait_sleep` | `wait_time` | Same input field: `seconds`. |

Removed alias calls now return `TOOL_NOT_FOUND` instead of being silently
redirected. Update MCP client prompts, saved workflows, and docs to use the
replacement names.

## Browser Requirements

DrissionPage MCP starts a local Chrome/Chromium browser through DrissionPage. Install one of the following before using browser-backed tools:

- Google Chrome
- Chromium
- A compatible Chromium-based browser supported by DrissionPage

If the browser is installed in a custom location, configure the browser path through your environment or DrissionPage configuration. See [Troubleshooting](troubleshooting.md) for diagnostics.

## Testing Matrix

The repository CI checks are intended to cover:

- Python package import and tool registration checks.
- Unit tests that do not require a live browser.
- MCP protocol tests that exercise stdio/list/call behavior without external network access.
- Package build validation.
- Browser integration tests on Chromium/Chrome against a deterministic local fixture; the tests skip with explicit diagnostics if the browser cannot launch.

## Deprecation Policy

For public tool contract changes:

1. Document the upcoming change in the release notes.
2. Add or update tests that describe the old and new behavior.
3. Remove deprecated behavior only in a documented breaking release.

# MCP Tool Contract

This document summarizes the public MCP tool contract exposed by DrissionPage MCP.

## Transport

DrissionPage MCP runs as a local stdio MCP server. MCP clients start the server process and communicate through standard input/output.

Minimal Codex CLI/IDE configuration (`~/.codex/config.toml`, or project `.codex/config.toml` in a trusted project):

```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

Minimal JSON MCP client configuration:

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

Codex source checkout configuration:

```toml
[mcp_servers.drissionpage]
command = "python"
args = ["-m", "drissionpage_mcp.cli"]
cwd = "/absolute/path/to/DrissionMCP"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

JSON source checkout configuration:

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "python",
      "args": ["-m", "drissionpage_mcp.cli"],
      "cwd": "/absolute/path/to/DrissionMCP"
    }
  }
}
```

## Response Shape

Tools return MCP content blocks plus a stable machine-readable result payload:

- The first text item starts with `### JSON_RESULT` and contains a fenced JSON object.
- When supported by the active MCP Python SDK, the same object is also returned as `structuredContent`.
- When supported by the active MCP Python SDK, each listed tool exposes a typed
  `outputSchema` envelope with a tool-specific success `data` schema.
- Successful results use `ok: true`; tool-execution failures use `ok: false` with `error.code` and `error.message`.
- Failure details may include `hints`: a list of machine-readable next steps with
  stable `action` identifiers and optional `tool`, `command`, or `env` fields.
- Human-readable MCP text content still follows as `### Result`, `### Error`, and optional `### Code` blocks.
- Screenshots include `ImageContent` with PNG data plus the JSON result block.
- Tool input schemas reject unknown fields. Typos such as `fullPage` instead of
  `full_page` return `MCP_ARGUMENT_INVALID` instead of being silently ignored.

Example failure payload:

```json
{
  "ok": false,
  "message": "Tool 'missing' not found",
  "error": {
    "code": "TOOL_NOT_FOUND",
    "message": "Tool 'missing' not found",
    "details": {
      "tool_name": "missing",
      "hints": [
        {
          "action": "list_available_tools",
          "message": "Call tools/list and use one of the public tool names."
        }
      ]
    }
  }
}
```

All tools share this base output envelope, while success `data` is typed per tool:

```json
{
  "ok": true,
  "message": "Operation completed successfully.",
  "data": {}
}
```

For failures, `error` contains `code`, `message`, and optional `details`.
Common runtime failures include structured recovery hints under
`error.details.hints`; for example, `ELEMENT_NOT_FOUND` can suggest
`page_snapshot`, `element_find_all`, `wait_for_element`, and iframe/dynamic
content checks.

Stable tool-execution error codes include `BROWSER_START_FAILED`, `BROWSER_NOT_INITIALIZED`, `PAGE_NAVIGATION_FAILED`, `ELEMENT_NOT_FOUND`, `SELECTOR_INVALID`, `TIMEOUT`, `SCREENSHOT_FAILED`, `POLICY_DENIED`, and `UNKNOWN_ERROR`. Protocol/validation diagnostics use `TOOL_NOT_FOUND` and `MCP_ARGUMENT_INVALID` where the SDK permits stable diagnostic data.

## Tool Annotations

The server marks tools with MCP annotations:

- Read-only tools use `readOnlyHint=true`.
- Browser or page mutation tools use `destructiveHint=true`.
- Advisory idempotent operations use `idempotentHint=true` where supported by the SDK.
- Tools operate on the open web, so `openWorldHint=true` is set.

## Tool Inventory

### Navigation

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `page_navigate` | Destructive | `url` | Open a URL in the active browser tab. |
| `page_go_back` | Destructive | none | Go back in browser history. |
| `page_go_forward` | Destructive | none | Go forward in browser history. |
| `page_refresh` | Destructive | none | Reload the current page. |

### Page Operations

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `page_resize` | Destructive | `width`, `height` | Resize the browser window. |
| `page_screenshot` | Read-only | none | Capture the viewport or full page. Optional: `full_page`, `path`. |
| `page_snapshot` | Read-only | none | Return a bounded page outline with text excerpt, headings, links, buttons, inputs, forms, counts, truncation metadata, and recommended selectors. Optional: `include_html`, `max_elements`, `max_text_chars`. |
| `page_click_xy` | Destructive | `x`, `y` | Click page coordinates. Optional: `element` description. |
| `page_close` | Destructive | none | Close the browser context. |
| `page_get_url` | Read-only | none | Return the current page URL. |

### Element Operations

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `element_find` | Read-only | `selector` | Find an element by CSS selector or XPath. Bare selectors are treated as CSS. Optional: `timeout` (default 3s). |
| `element_find_all` | Read-only | `selector` | Find multiple matching elements with bounded text, attributes, optional HTML, count/truncation metadata, and recommended selectors. Optional: `limit` (default 20), `include_html`. |
| `element_click` | Destructive | `selector` | Click an element selected by CSS/XPath/explicit DrissionPage locator. Optional: `timeout`. |
| `element_type` | Destructive | `selector`, `text` | Type text into an element selected by CSS/XPath/explicit DrissionPage locator. Optional: `timeout`, `clear`. |
| `element_get_text` | Read-only | none | Get page text, or element text when `selector` is set. |
| `element_get_attribute` | Read-only | `selector`, `attribute` | Read an HTML attribute. |
| `element_get_property` | Read-only | `selector`, `property` | Read a live DOM property such as `value`. |
| `element_get_html` | Read-only | none | Get page HTML, or element HTML when `selector` is set. |

### Wait Operations

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `wait_for_element` | Read-only | `selector` | Wait for an element to load. Bare selectors are treated as CSS. Optional: `timeout`. |
| `wait_for_url` | Read-only | `url_pattern` | Wait until the current URL contains text. Optional: `timeout`. |
| `wait_time` | Read-only | `seconds` | Sleep for a fixed duration. |

## Resources

The server exposes deterministic JSON resources:

| URI | Purpose |
| --- | --- |
| `drissionpage://session/summary` | Browser/session activity, tab count, current URL, and policy flags. |
| `drissionpage://page/current` | Bounded current page title, URL, text excerpt, and HTML excerpt. |
| `drissionpage://tools/catalog` | Public tool catalog with annotations and output data schema names. |
| `drissionpage://policy/summary` | Redacted local safety policy summary. |

Resource caps:

- page text excerpt: 4000 characters
- page HTML excerpt: 8000 characters
- resource JSON payload target maximum: 12000 characters

## Prompts

The server exposes user-controlled workflow prompts:

| Prompt | Purpose |
| --- | --- |
| `browser_navigate_and_summarize` | Navigate, inspect text, and summarize with source URL. |
| `browser_extract_structured_data` | Navigate, inspect text/HTML, and return schema-shaped JSON. |
| `browser_fill_form_safely` | Fill forms with confirmation guidance before submission. |
| `browser_debug_page_issue` | Gather page text/HTML/screenshot evidence for debugging. |

## Compatibility Notes

- Selectors are normalized before calling DrissionPage: bare selectors are treated as CSS (`h1` -> `css:h1`, `input[name=q]` -> `css:input[name=q]`), XPath-looking strings are prefixed as XPath (`//h1` -> `xpath://h1`), and explicit DrissionPage forms such as `tag:h1`, `text:Submit`, `css:...`, `xpath:...`, and `@name=value` are preserved.
- Tool responses include selector metadata: `selector`, `locator`, `selector_strategy`, and `selector_normalized`.
- `page_snapshot` and `element_find_all` are preview page-understanding tools. Their outputs are intentionally bounded and include truncation metadata so clients can request narrower selectors instead of pulling full-page HTML by default. `page_snapshot.max_elements` remains a total cap, and the server balances that cap across headings, links, buttons, inputs, and forms before filling remaining capacity.
- A browser tab must exist before read-only page/element tools can inspect content. Use `page_navigate` first in a fresh session.
- `element_input_text` and `wait_sleep` were removed in 0.4.0. Use
  `element_type` and `wait_time`.

## Optional Local Safety Policy

By default, DrissionPage MCP remains a local stdio browser automation server with open navigation behavior. Operators can opt in to stricter controls with environment variables:

| Variable | Effect |
| --- | --- |
| `DP_MCP_NAV_ALLOWLIST` | Comma-separated host names or URL prefixes. When set, navigation is allowlist-first. |
| `DP_MCP_NAV_BLOCKLIST` | Comma-separated host names or URL prefixes rejected after allowlist checks. |
| `DP_MCP_BLOCK_PRIVATE_NETWORK` | Set to `1`, `true`, or `yes` to reject localhost/private/link-local navigation. |
| `DP_MCP_SCREENSHOT_ROOT` | Restrict `page_screenshot.path` saves to this directory tree. |

Denied navigation is checked before `context.ensure_tab()`, so policy rejection does not start or initialize a browser.

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
- Human-readable MCP text content still follows as `### Result` or `### Error` blocks.
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

Stable tool-execution error codes include `BROWSER_START_FAILED`, `BROWSER_NOT_INITIALIZED`, `PAGE_NAVIGATION_FAILED`, `ELEMENT_NOT_FOUND`, `SELECTOR_INVALID`, `TIMEOUT`, `SCREENSHOT_FAILED`, `POLICY_DENIED`, `UNSUPPORTED_OPERATION`, and `UNKNOWN_ERROR`. Protocol/validation diagnostics use `TOOL_NOT_FOUND` and `MCP_ARGUMENT_INVALID` where the SDK permits stable diagnostic data.

## Tool Annotations

The server marks tools with MCP annotations:

- Read-only tools use `readOnlyHint=true`.
- Browser or page mutation tools use `destructiveHint=true`.
- Advisory idempotent operations use `idempotentHint=true` where supported by the SDK.
- Tools operate on the open web, so `openWorldHint=true` is set.

## Tool Inventory

The 0.7.4 registry contains 56 typed browser tools. Site, component, challenge,
and business workflows are composed by clients or optional external Skills.

### Network Listener Beta

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `network_listen_start` | Destructive | none | Start DrissionPage 4.x network observation for HTTP/XHR/Fetch packets. No interception or mocking. Optional: `targets`, `is_regex`, `method`, `resource_type`, `clear`. |
| `network_listen_wait` | Read-only | none | Wait for bounded network packets with URL, method, resource type, status, MIME type, optional redacted headers, and optional bounded body excerpts. Optional: `timeout`, `limit`, `include_headers`, `include_body`, `max_body_chars`. |
| `network_listen_stop` | Destructive | none | Stop network observation and optionally clear the listener queue. Optional: `clear`. |

### Navigation

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `page_navigate` | Destructive | `url` | Open a URL in the active browser tab. Optional: `new_tab`, `observe`. |
| `page_go_back` | Destructive | none | Go back in browser history. |
| `page_go_forward` | Destructive | none | Go forward in browser history. |
| `page_refresh` | Destructive | none | Reload the current page. |

### Tab Operations

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `tab_list` | Read-only | none | List open browser tabs with stable MCP tab IDs, native tab IDs, URLs, titles, and active state. |
| `tab_switch` | Destructive | `tab_id` | Switch to a tab returned by `tab_list`. |
| `tab_close` | Destructive | `tab_id` | Close one browser tab without closing the whole browser. |

### Page Operations

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `page_resize` | Destructive | `width`, `height` | Resize the browser window. |
| `page_screenshot` | Read-only | none | Capture an inline viewport or full-page screenshot. Optional: `full_page`. |
| `page_screenshot_save` | Destructive | `path` | Save a viewport or full-page screenshot under `DP_MCP_SCREENSHOT_ROOT`. Optional: `full_page`. |
| `page_snapshot` | Read-only | none | Return a bounded page outline with text excerpt, headings, links, buttons, inputs, forms, counts, truncation metadata, and recommended selectors. Optional: `include_html`, `max_elements`, `max_text_chars`. |
| `page_observe` | Read-only | none | Return a compact page fingerprint with URL, title, ready state, element counts, visible text samples, active element, recent console summary, and limits. Optional: `max_texts`, `max_text_chars`. |
| `page_evaluate` | Destructive | `script` | Run a bounded JavaScript function body in the current page and return a JSON-safe result. Optional: `args`, `max_chars`. |
| `page_scroll` | Destructive | none | Scroll the page by direction or to a position. Optional: `direction`, `pixels`, `x`, `y`. |
| `keyboard_press` | Destructive | `keys` | Send keys to the active page element. Optional: `interval`. |
| `page_pointer_move` | Destructive | `x`, `y` | Move to exact viewport CSS coordinates without pressing a button. Optional: `profile` (`direct` default or deterministic 24-step `natural`) and `element`. |
| `page_pointer_drag` | Destructive | `start_x`, `start_y`, `end_x`, `end_y` | Perform one failure-safe held drag with exact endpoints. Optional: up to six ordered `waypoints`, `profile` (`direct` or `natural`), `element`, and `button`. |
| `page_pointer_drag_element` | Destructive | `source`, `destination` | Resolve CSS/XPath geometry immediately before an element, offset, or track-ratio drag. Supports one same-origin iframe and CSS paths through nested open Shadow DOM hosts. Optional: `profile` and `button`. |
| `page_click_xy` | Destructive | `x`, `y` | Move with the `direct` or deterministic bounded `natural` profile, optionally wait for `delay_before_press_ms`, then press and release at the exact viewport target. Optional: `profile`, `element`, and `button`. |
| `page_close` | Destructive | none | Close the browser context. |
| `page_get_url` | Read-only | none | Return the current page URL. |
| `page_dialog_respond` | Destructive | `action` | Accept or dismiss one currently pending alert, confirm, or prompt through a capability-probed native path. Optional: `prompt_text`, `timeout`. Prompt text is never returned. |

### Debug / Observability

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `page_console_logs` | Read-only | none | Read bounded browser console messages from the current tab. Optional: `level`, `since`, `limit`. |

### Element Operations

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `element_find` | Read-only | `selector` | Find an element by CSS selector or XPath. Bare selectors are treated as CSS. Optional: `timeout` (default 3s). |
| `element_find_all` | Read-only | `selector` | Find multiple matching elements with bounded text, attributes, optional HTML, count/truncation metadata, and recommended selectors. Optional: `limit` (default 20), `include_html`. |
| `element_click` | Destructive | `selector` | Click an element selected by CSS/XPath/explicit DrissionPage locator. Optional: `timeout`, `observe`, `button` (`left`, `right`, `middle`), `click_count` (`1`, `2`). Existing calls remain left single-clicks. Unsupported native variants return `UNSUPPORTED_OPERATION` rather than substituting another click. |
| `element_click_and_download` | Destructive | `selector` | Perform one native click and await one correlated completed download under `DP_MCP_DOWNLOAD_ROOT`. Returns an integrity-checked `ArtifactRef` and linked `ActionReceipt`. Optional: `operation_key`, `timeout`, `expected_filename`, `expected_mime_type`. |
| `element_type` | Destructive | `selector`, `text` | Type text into an element selected by CSS/XPath/explicit DrissionPage locator. Optional: `timeout`, `clear`, `observe`. |
| `element_upload_file` | Destructive | `selector`, `paths` | Upload one or more files from `DP_MCP_UPLOAD_ROOT` into an `input[type=file]`. Optional: `timeout`. |
| `element_scroll_into_view` | Destructive | `selector` | Scroll an element into the viewport. Optional: `center`, `timeout`. |
| `element_hover` | Destructive | `selector` | Hover an element. Optional: `timeout`, `offset_x`, `offset_y`. |
| `element_select` | Destructive | `selector`, `value` | Select an option from a `<select>` by value, text, or index. Optional: `by`, `timeout`. |
| `element_check` | Destructive | `selector` | Check or uncheck checkbox/radio controls. Optional: `checked`, `by_js`, `timeout`. |
| `element_get_text` | Read-only | none | Get page text, or element text when `selector` is set. |
| `element_get_attribute` | Read-only | `selector`, `attribute` | Read an HTML attribute. |
| `element_get_property` | Read-only | `selector`, `property` | Read a live DOM property such as `value`. |
| `element_get_html` | Read-only | none | Get page HTML, or element HTML when `selector` is set. |

### Frame / Shadow DOM

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `frame_list` | Read-only | none | List iframe/frame contexts without changing any global current-frame state. Optional: `limit`. |
| `frame_snapshot` | Read-only | none | Return a bounded outline from one iframe selected by `frame_selector` or `frame_index`. |
| `frame_find` | Read-only | `selector` | Find one element inside an iframe selected by `frame_selector` or `frame_index`. |
| `shadow_find` | Read-only | `host_selector`, `selector` | Find one element inside a shadow root exposed by the current supported DrissionPage runtime. The tested 4.x path includes open and closed roots. |
| `shadow_find_all` | Read-only | `host_selector`, `selector` | Find repeated elements inside a shadow root exposed by the supported DrissionPage runtime. Optional: `limit`, `include_html`. |

### Cookies and Storage

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `browser_cookies_get` | Read-only | none | Read normalized cookies. Values are redacted unless `include_values=true`. |
| `browser_cookies_set` | Destructive | `cookies` | Set a bounded batch of 1-100 cookies through DrissionPage. Successful results echo Cookie values by default for MCP callbacks. |
| `browser_cookies_delete` | Destructive | `name` | Delete one named Cookie. Optional: `url`, `domain`, `path`. |
| `browser_cookies_clear` | Destructive | none | Clear all browser Cookies. |
| `storage_get` | Read-only | none | Read localStorage/sessionStorage by optional `key`. Optional: `area`, `include_values`. |
| `storage_set` | Destructive | `key`, `value` | Set one localStorage/sessionStorage value. The value is not echoed in the response. Optional: `area`. |
| `storage_clear` | Destructive | none | Clear one storage key or the whole selected storage area. Optional: `area`, `key`. |

### Wait Operations

| Tool | Type | Required input | Description |
| --- | --- | --- | --- |
| `wait_for_element` | Read-only | `selector` | Wait for an element to load. Bare selectors are treated as CSS. Optional: `timeout`. |
| `wait_for_url` | Read-only | `url_pattern` | Wait until the current URL contains text. Optional: `timeout`. |
| `wait_until` | Read-only | `condition` | Wait for observable conditions: `present`, `visible`, `hidden`, `detached`, `clickable`, `stable`, `text_contains`, `text_matches`, `url_contains`, or `url_matches`. Optional: `selector`, `value`, `timeout`, `interval`, `stable_ms`. |
| `wait_time` | Read-only | `seconds` | Sleep for a fixed duration. |

## Resources

The server exposes one deterministic JSON resource that does not initialize a
browser or perform a network request:

| URI | Purpose |
| --- | --- |
| `drissionpage://skills/catalog` | Versioned discovery metadata for optional Skills published outside the Python distribution. It declares the `skills/` catalog path and `skills/<skill-name>/SKILL.md` entrypoint convention. |

Resource caps:

- Skills catalog JSON maximum: 4000 characters

## Prompts

DrissionPage MCP 0.7.4 exposes no MCP prompts. `tools/list`, typed schemas, and
typed errors describe the standalone core; procedural guidance belongs in
optional Skills.

## Compatibility Notes

- Selectors are normalized before calling DrissionPage: bare selectors are treated as CSS (`h1` -> `css:h1`, `input[name=q]` -> `css:input[name=q]`), XPath-looking strings are prefixed as XPath (`//h1` -> `xpath://h1`), and explicit DrissionPage forms such as `tag:h1`, `text:Submit`, `css:...`, `xpath:...`, and `@name=value` are preserved.
- Tool responses include selector metadata: `selector`, `locator`, `selector_strategy`, and `selector_normalized`.
- `page_snapshot` and `element_find_all` include `meta.approx_tokens`, `meta.json_chars`, and `meta.truncated` so clients can narrow later calls when a response is large.
- `page_snapshot` and `element_find_all` are preview page-understanding tools. Their outputs are intentionally bounded and include truncation metadata so clients can request narrower selectors instead of pulling full-page HTML by default. `page_snapshot.max_elements` remains a total cap, and the server balances that cap across headings, links, buttons, inputs, and forms before filling remaining capacity.
- Form and component workflows are composed from element discovery, type/select/check/click/keyboard, upload, wait, and state-read tools. The core does not classify widget libraries or infer business submission intent.
- `page_dialog_respond` handles one currently pending JavaScript dialog. Capability gaps return `UNSUPPORTED_OPERATION`; prompt text and dialog messages are not retained in action history.
- `element_click_and_download` requires an approved `DP_MCP_DOWNLOAD_ROOT`. A successful response includes one checksum-verified regular file, safe relative path, sanitized HTTP(S) source URL, `ArtifactRef`, and correlated `ActionReceipt`. Replaying the same operation key does not click again; failure and indeterminate results contain no artifact.
- `tab_list` synchronizes with browser tabs opened by normal page behavior, including `target="_blank"` links.
- `page_observe` is designed for compact state checks. Use `page_snapshot` when you need selectors and structured page outline details. Its `console` field summarizes recent current-tab console messages when DrissionPage console capture is available.
- `page_console_logs` returns normalized console messages with `index`, `level`, `text`, `url`, `line`, `column`, and `source`. Use `since` with the previous `next_cursor` to fetch only newer messages.
- `page_evaluate` accepts a JavaScript function body; use `return` for values you want in `structuredContent.data.result`. The result is bounded by `max_chars`.
- `element_upload_file` requires `DP_MCP_UPLOAD_ROOT`; absolute input paths are accepted only when they resolve inside that root, and successful responses return file names rather than absolute paths.
- `frame_*` tools are stateless: each call selects by `frame_selector` or zero-based `frame_index`; no global current-frame mode is stored. The DrissionPage 4.x browser path is regression-tested against an attached cross-origin OOPIF.
- `shadow_*` tools use DrissionPage's native shadow-root object instead of page-JavaScript `host.shadowRoot`. The current supported DrissionPage 4.x path is regression-tested against both open roots and a closed root that is invisible to page JavaScript. Capability failure is reported; the MCP does not inject a piercing fallback.
- `page_pointer_drag_element` has a different implementation boundary: its synchronous page script remains limited to the top document or one same-origin iframe and nested open Shadow DOM hosts.
- `browser_cookies_get` redacts cookie values by default. Use `include_values=true` only when the MCP client/session is allowed to handle cookie secrets.
- `browser_cookies_set` accepts `name`, `value`, optional `url`, `domain`, `path`, `expires`, `secure`, `http_only`, `same_site`, `priority`, and `source_scheme`. Its successful result echoes values by default, so callbacks and logs must be allowed to handle Cookie secrets.
- `browser_cookies_delete` and `browser_cookies_clear` use DrissionPage's browser Cookie setter directly; they require no user-side browser action and no tool-loading profile.
- `storage_set` does not echo the stored value in its success payload.
- `observe=true` on `page_navigate`, `element_click`, and `element_type` adds an optional `changes` field with URL/title changes, count deltas, appeared/removed text samples, active element, `console_errors_added`, `console_warnings_added`, and `new_console_messages`. It is omitted by default.
- `wait_until` is the preferred recovery path for dynamic UI state such as delayed clickability, disappearing spinners, stable elements, text updates, or URL transitions.
- Pointer tools default to `profile="direct"`. `profile="natural"` uses a fixed,
  reproducible 24-step eased cubic path with bounded 8-14ms intervals and an exact final
  point. It changes one pointer action's execution semantics; it does not decide
  targets, challenges, or business workflow progression.
- A browser tab must exist before read-only page/element tools can inspect content. In a fresh session, call `page_navigate`, then collect `page_snapshot` or `page_observe` as a separate explicit step.
- Challenge observation, verified multi-click sequences, and site/business rules
  belong in external `skills/<skill-name>/SKILL.md` procedures and must use public
  MCP tools only.
- `element_input_text` and `wait_sleep` were removed in 0.4.0. Use
  `element_type` and `wait_time`.

## Optional Local Safety Policy

By default, DrissionPage MCP remains a local stdio browser automation server with open navigation behavior. Operators can opt in to stricter controls with environment variables:

| Variable | Effect |
| --- | --- |
| `DP_MCP_NAV_ALLOWLIST` | Comma-separated host names or URL prefixes. When set, navigation is allowlist-first. |
| `DP_MCP_NAV_BLOCKLIST` | Comma-separated host names or URL prefixes rejected after allowlist checks. |
| `DP_MCP_BLOCK_PRIVATE_NETWORK` | Set to `1`, `true`, or `yes` to reject localhost/private/link-local navigation. |
| `DP_MCP_SCREENSHOT_ROOT` | Required root directory for `page_screenshot_save` file writes. |
| `DP_MCP_UPLOAD_ROOT` | Required root directory for `element_upload_file` input files. |
| `DP_MCP_DOWNLOAD_ROOT` | Required approved root for `element_click_and_download` artifacts. Public results expose safe relative paths only. |
| `DP_MCP_DENY_DOWNLOAD` | Deny `element_click_and_download` before the native click or filesystem allocation. |

Denied navigation is checked before `context.ensure_tab()`, so policy rejection does not start or initialize a browser.

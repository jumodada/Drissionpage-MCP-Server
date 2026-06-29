---
name: drissionpage-mcp-error-contracts
description: Preserve stable MCP structured errors, selector semantics, and no-compat-alias policy.
---

# MCP Error Contracts Skill

Use this when changing tool handlers, selector behavior, or MCP response shape.

## Structured response contract

Every tool result should expose a machine-readable payload through:

- first text block starting with `### JSON_RESULT`
- `structuredContent` when supported by the MCP SDK
- stable `ok`, `message`, `data` or `error` fields
- typed `outputSchema` when supported by the MCP SDK

Tool execution failures should return `ok: false` and a stable error code. Do not leak raw exceptions as the only signal.

## Important bug lesson: classify original exceptions

`tool_errors` must classify the original exception object, not only the formatted user-facing message.

Why: wrapping `TimeoutError` as a generic string can turn a real timeout into `UNKNOWN_ERROR`.

Correct pattern:

```python
except Exception as exc:
    error_message = message(exc) if callable(message) else f"{message}: {exc}"
    response.add_error(error_message, classify_error(exc))
```

Keep the human message helpful, but preserve machine-readable error semantics.

## Error code expectations

Common mappings:

- missing element -> `ELEMENT_NOT_FOUND`
- invalid selector syntax -> `SELECTOR_INVALID`
- timeout / timed out / `TimeoutError` -> `TIMEOUT`
- no active tab / uninitialized browser -> `BROWSER_NOT_INITIALIZED`
- navigation failure -> `PAGE_NAVIGATION_FAILED`
- screenshot failure -> `SCREENSHOT_FAILED`
- policy/allowlist/blocklist denial -> `POLICY_DENIED`
- browser launch/start/initialize failure -> `BROWSER_START_FAILED`
- unknown tool or removed alias -> `TOOL_NOT_FOUND`
- invalid MCP arguments -> `MCP_ARGUMENT_INVALID`

## Selector semantics

Bare selectors should be LLM-friendly CSS by default:

- `h1` -> `css:h1`
- `input[name=q]` -> `css:input[name=q]`

Preserve explicit DrissionPage locator forms:

- `tag:h1`
- `text:Submit`
- `xpath://h1`
- `@name=value`

Tool responses should include selector metadata where relevant:

- original `selector`
- normalized `locator`
- `selector_strategy`
- `selector_normalized`

## No compatibility aliases unless explicitly approved

The public alias tools were removed:

- `element_input_text` -> use `element_type`
- `wait_sleep` -> use `wait_time`

Do not reintroduce compatibility shims or alternate public input aliases unless the maintainer explicitly changes the policy.

Example: `element_get_property` uses public input field `property`, not `property_name`.

## Tests to keep

Maintain tests for:

- missing selector structured errors
- URL wait timeout as `TIMEOUT`
- removed aliases returning `TOOL_NOT_FOUND` with suggested replacement
- selector normalization in real browser tests
- output schema and JSON mirror contracts

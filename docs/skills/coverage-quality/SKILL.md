---
name: drissionpage-mcp-coverage-quality
description: Raise DrissionPage MCP test coverage through meaningful MCP/browser scenarios and contract tests, not superficial line coverage.
---

# Coverage Quality Skill

Use this when coverage needs to increase or when CI coverage fails.

## Goal

Raise coverage by protecting real behavior:

1. Browser-backed MCP workflows.
2. PageTab failure and compatibility paths.
3. Context/compat/doctor lifecycle contracts.
4. Response/server/resource protocol boundaries.

Avoid tests that merely import modules, call private helpers with no user-facing meaning, or assert implementation trivia.

## Proven coverage path

### P0 — Real MCP browser workflows

Add deterministic local-browser tests in `tests/test_browser_integration.py` using `tests/fixtures/http_fixture.py`.

High-value flows:

- Form fill and submit:
  - `page_navigate`
  - `element_find`
  - `element_type`
  - `element_get_property`
  - `element_click`
  - `wait_for_url`
  - `element_get_text`
- Dynamic DOM:
  - navigate to a local JS page
  - `wait_for_element`
  - read the rendered element
- Structured recovery:
  - missing selector returns `ELEMENT_NOT_FOUND`
  - URL wait timeout returns `TIMEOUT`
  - first content block starts with `### JSON_RESULT`

Keep these tests local and deterministic; do not use public websites for the default suite.

### P1 — PageTab behavior

Use fake DrissionPage-like objects in `tests/test_tab.py` to cover real edge paths:

- `wait` succeeds but the second element lookup fails.
- page text fallback to `tag:body` when `.text` is unavailable.
- screenshot fallback for older DrissionPage builds.
- screenshot temporary file cleanup is best-effort.
- URL polling and polling-error behavior.
- action failures for back/forward/refresh/click/resize.
- `doc_loaded` signature compatibility fallback.
- close errors are logged/swallowed where the public contract says cleanup should not raise.

### P2 — Environment and lifecycle contracts

Add or maintain tests for:

- `DrissionPageContext` idempotent initialization, tab promotion, cleanup, and failure paths.
- `compat.py` Chromium vs ChromiumPage fallback, environment variables, new-tab signatures, and browser quit/close variants.
- `doctor.py` version fallback, browser discovery, old Python hints, and launch success/failure.

### P3 — MCP protocol contracts

Add or maintain tests for:

- `ToolResponse` error/content defaults, screenshot metadata, image inputs, and error classification.
- `DrissionPageMCPServer._call_tool_impl` success, validation, unknown tool, removed alias, and unexpected exception paths.
- `run_server()` cleanup in `finally`.
- resource unknown URI, truncation, and safe attribute access.

## Coverage gate

After meaningful tests raise total coverage above 95%, update:

```toml
[tool.coverage.report]
fail_under = 95
```

Do not raise the gate unless CI-like full coverage passes locally.

## Verification

Run:

```bash
python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml:coverage.xml -q
DP_MCP_REQUIRE_BROWSER=1 python -m pytest tests/test_browser_integration.py -q
```

Then run lint/type checks before reporting completion.

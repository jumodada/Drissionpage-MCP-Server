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
- DrissionPage 5.x beta/internal builds are not supported by DrissionPage MCP
  0.7.5. Keep MCP installs pinned to `DrissionPage>=4.1.1.4,<5` until a
  separate compatibility plan is implemented.
- Input schema changes should be backward compatible when possible. The 0.4.1 `element_get_property` `property_name` -> `property` cleanup is a documented beta-stage breaking schema correction for LLM usability.
- Unknown input fields are rejected rather than silently ignored. Update saved
  MCP workflows to use the documented snake_case field names exactly.
- Tool responses are text/image MCP content blocks. Human-readable wording may change, but success and error responses should remain explicit.
- Browser behavior can vary by Chrome/Chromium version, site content, extensions, and local security settings.

## Current Frame And Shadow Boundaries

- `frame_list`, `frame_find`, and `frame_snapshot` use DrissionPage frame objects
  and are regression-tested against an attached cross-origin OOPIF. The parent
  page cannot read that fixture through `iframe.contentDocument`.
- `shadow_find` and `shadow_find_all` use DrissionPage's native shadow-root object.
  Supported DrissionPage 4.x runtimes are regression-tested against both open and
  closed roots; the closed fixture remains invisible through page-JavaScript
  `host.shadowRoot`.
- These capabilities do not use JavaScript piercing fallbacks. An unsupported
  runtime fails instead of returning an empty successful result.
- Selector-backed pointer geometry remains narrower: one same-origin iframe and
  nested open Shadow DOM paths only. Do not infer pointer support from the
  broader read-only `frame_*` and `shadow_*` evidence.

## 0.7.4 to 0.7.5 Migration

0.7.5 adds four default-registered browser request-environment tools and grows
the ordered registry from 56 to 60 tools. All tools load automatically; there is
no capability profile and users do not select a `full` mode.

- `browser_headers_set` replaces the current tab's extra request headers. It
  accepts at most 64 strictly validated names and values; an empty object clears
  the configured headers.
- `browser_user_agent_set` overrides the current tab's user agent and optional
  platform metadata. Its result includes both the accepted value and the
  previous user agent so browser-only workflows can restore it explicitly.
- `network_blocked_urls_set` replaces up to 100 URL patterns; an empty list
  clears all configured patterns.
- Successful header, user-agent, and blocked-URL writes echo accepted values by
  default for MCP callbacks and verification. Clients must treat sensitive
  header values as secrets.
- `browser_cache_clear` clears only the HTTP cache. Cookies, localStorage, and
  sessionStorage are explicitly preserved.

## 0.7.3 to 0.7.4 Migration

0.7.4 adds three default-registered Cookie mutation tools and grows the ordered
registry from 53 to 56 tools. There is no capability profile and users do not
select a `full` mode.

- `browser_cookies_set` accepts a bounded batch of 1-100 cookies and maps public
  snake_case fields such as `http_only`, `same_site`, and `source_scheme` to the
  DrissionPage 4.x setter contract.
- Successful `browser_cookies_set` results echo Cookie values by default for MCP
  callback and verification flows. Clients must treat those result payloads as
  secrets.
- `browser_cookies_delete` deletes one exact name with optional `url`, `domain`,
  and `path` scope. `browser_cookies_clear` clears the browser Cookie store.
- `browser_cookies_get` remains backward compatible and continues to redact
  values unless `include_values=true`.

## 0.7.0 to 0.7.1 Migration

0.7.1 keeps the 62-tool public registry and does not add a new user-facing capability family.

- Repeated native text input uses `clear(by_js=True)` before real DrissionPage input, avoiding the DrissionPage 4.1 Linux key-chord clear path.
- W01-W08 is now executable through the public MCP tool path. Run `python -m tests.evals.task_completion_benchmark --iterations 10` with a local Chromium browser for the release gate.
- `TaskContext.retry_limit` remains a compatibility field for future explicit retry lineage. The 0.7 runtime never retries an action automatically.
- The release does not introduce table/grid extraction, `PageModel`, public `TargetRef`, checkpoint persistence, or a workflow DSL.

## 0.7.1 to 0.7.2 Migration

0.7.2 intentionally narrows the public registry from 62 to 53 generic browser
tools. It removes component-library, challenge, and convenience-workflow
orchestration from the core package.

| Removed tool | Compose instead |
| --- | --- |
| `form_inspect` | `page_snapshot`, `element_find_all`, `element_find`, and attribute/property/text reads |
| `form_fill` | explicit `element_type`, `element_select`, `element_check`, `element_click`, and `keyboard_press`, followed by state reads |
| `form_fill_preview` | the same atomic actions without the final activation step |
| `form_submit` | explicit click or keyboard activation followed by `wait_until`, URL, DOM, text, or property verification |
| `page_detect_challenges` | `page_observe`, `page_snapshot`, focused element reads, and optional Skill classification |
| `page_click_xy_batch` | individual `element_click` or `page_click_xy` calls with fresh evidence and verification between actions |
| `page_wait_challenge_result` | `wait_until` plus focused URL, text, attribute, or property postconditions |
| `browser_open_and_snapshot` | `page_navigate`, then explicit `page_snapshot` or `page_observe` |
| `browser_extract_links` | bounded `element_find_all` link discovery |

- No aliases or placeholder tools are registered.
- `DP_MCP_DENY_EXTERNAL_SUBMISSION` is removed because generic click and keyboard tools can also submit. Treating one named workflow as the only submission boundary created false assurance.
- `ActionReceipt` remains for timing-critical downloads and native dialog responses. Ordinary DOM mutations are verified through explicit state reads.
- Pointer tools default to `profile="direct"`. The optional `natural` profile is a
  deterministic 24-step eased cubic path with reproducible 8-14ms intervals and an exact target;
  randomized jitter, overshoot, reaction/hold timing, `precise`, and explicit
  synthetic start-coordinate fields are removed.
- MCP prompts are removed. The only resource is the static
  `drissionpage://skills/catalog`, which declares the external
  `skills/<skill-name>/SKILL.md` directory convention without installing or
  executing Skills.
- Reusable form, challenge-observation, verified multi-click, and site/business
  recipes are available as optional Skills outside the wheel and sdist.

## 0.6.2 to 0.7.0 Migration

0.7.0 additively grows the public registry from 58 to 62 tools and preserves existing tool names and defaults.

- `form_fill` fills and verifies supported native/rich controls without submitting; `form_submit` owns the external submission boundary and returns an `ActionReceipt`.
- A clearly authorized task may call `form_submit` without a redundant confirmation round. `form_fill_preview` remains unchanged for preview-only/no-submit flows.
- Optional `operation_key` values prevent a second live-task invocation for matching `form_submit` and `element_click_and_download` requests. This is not a restart-safe or remote exactly-once guarantee.
- `page_dialog_respond` and enriched `element_click` variants are capability-probed. Unsupported native behavior returns `UNSUPPORTED_OPERATION` rather than a substituted action.
- `element_click_and_download` requires `DP_MCP_DOWNLOAD_ROOT` and returns safe relative paths, SHA-256, bounded metadata, and a correlated `ArtifactRef`/receipt.
- The W01-W08 ten-run reliability benchmark and remaining coverage/stability expansion are scheduled for 0.7.1; 0.7.0 claims browser-backed feature coverage, not that ten-run threshold.

## 0.6.1 to 0.6.2 Migration

0.6.2 additively extends `page_pointer_drag` with up to six optional ordered `waypoints`. Existing calls without `waypoints` retain their input and output behavior.

- The public registry remains at 58 tools.
- One button press is held through every waypoint and released once at the final target.
- All segments use the drag's existing `profile` and `button`; per-waypoint pauses or profiles are not supported.
- Selector-backed drags continue to use `page_pointer_drag_element`.

## 0.6.0 to 0.6.1 Migration

0.6.1 adds `page_pointer_drag_element` and changes `page_pointer_drag` motion metadata to expose reaction, grip, movement, micro-pause, overshoot/correction, and release phases. Pointer tool definitions now live in `tools/pointer.py`; no forwarding imports remain in `tools/common.py`.

- Public registry grows to 58 tools.
- Use `page_pointer_drag_element` for stable CSS/XPath source and destination paths.
- Use destination `track_ratio` for a known thumb and track.
- Use `page_pointer_drag` only when coordinates come from fresh visual evidence.
- CSS/XPath is supported in the top document or one same-origin iframe; nested open Shadow DOM hosts require CSS paths. Closed Shadow DOM and cross-origin iframe internals are not promised.

## 0.5.9 to 0.6.0 Migration

0.6.0 adds three autonomous visual orchestration tools and extends existing schemas additively:

- `page_detect_challenges`, `page_click_xy_batch`, and `page_wait_challenge_result` are new.
- `page_click_xy.delay_before_press_ms` defaults to zero.
- `wait_until` adds attribute/property equals and non-empty conditions plus optional `name`.
- The public registry grows to 57 tools.

## 0.5.8 to 0.5.9 Migration

0.5.9 is additive and intentionally exposes no persistent pointer-button state:

- `page_pointer_move` adds natural viewport movement without clicking.
- `page_pointer_drag` performs approach, press, held-button drag, and release in one failure-safe call.
- Models should use selector tools first, then choose move, click, or drag by visual interaction intent.
- The public registry grows to 54 tools; existing `page_click_xy` inputs remain unchanged.

## 0.5.7 to 0.5.8 Migration

0.5.8 intentionally upgrades the existing `page_click_xy` contract without a legacy wrapper:

- Coordinate inputs now accept viewport CSS-pixel floats and reject negative values.
- `profile` defaults to `natural`; `precise` and `direct` are explicit alternatives.
- Optional `start_x` and `start_y` must be supplied together.
- Successful output now includes typed `motion` metadata.
- The former direct interaction-level coordinate-click implementation is removed; saved clients should call the same `page_click_xy` tool with `profile="direct"` only when immediate movement is explicitly desired.

## 0.5.4 to 0.5.7 Migration

0.5.7 is additive for DrissionPage 4.x users. It keeps the 0.5.6 public tool
surface and adds guidance-only AI/client ergonomics improvements:

- The public tool registry grows to 52 tools.
- New workflow helpers are additive: `browser_open_and_snapshot`, `browser_extract_links`, and `form_fill_preview`.
- Network listener beta is observe-only for HTTP/XHR/Fetch through `network_listen_start`, `network_listen_wait`, and `network_listen_stop`; interception and mocking remain out of scope.
- `drissionpage://session/config` reports redacted browser/profile configuration.
- `drissionpage://guide/model-usage` and MCP prompts now prefer workflow-first tool routes before low-level primitives.
- `drissionpage://tools/catalog` includes tool descriptions to improve AI tool selection without changing public schemas.
- Recovery hints can point clients to `browser_open_and_snapshot`, `drissionpage://tools/catalog`, or `drissionpage://guide/model-usage` before retrying.
- File upload requires `DP_MCP_UPLOAD_ROOT` and never echoes absolute file paths.
- Cookie values are redacted by default in `browser_cookies_get`.
- `drissionpage://session/state` exposes only cookie names and storage keys.
- `drissionpage-mcp doctor` reports DrissionPage 5.x as unsupported.
- No 0.5.7 public tool, input schema, `JSON_RESULT`, `structuredContent`, or typed `outputSchema` migration is required.

## 0.4.0 to 0.4.1 Migration

| 0.4.0 input | 0.4.1 input | Notes |
| --- | --- | --- |
| `element_get_property` `property_name` | `element_get_property` `property` | The old field is rejected; update saved MCP workflows and prompts. |
| Bare DrissionPage text-like selectors | Explicit `text:...` | Bare selectors are now normalized as CSS. Use `text:Submit` for text matching. |

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
- Browser integration tests on Chromium/Chrome against deterministic local fixtures and the shared `DrissionPage-test-site` SSR fixture when `DP_TEST_SITE_URL` is configured; the tests skip with explicit diagnostics if the browser cannot launch.

## Deprecation Policy

For public tool contract changes:

1. Document the upcoming change in the release notes.
2. Add or update tests that describe the old and new behavior.
3. Remove deprecated behavior only in a documented breaking release.

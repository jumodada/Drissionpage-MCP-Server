---
name: turnstile-testing
description: Use when testing an authorized Cloudflare Turnstile integration or operating an authorized production challenge with drissionpage-mcp. Covers official visible, invisible, pass, fail, and forced-interactive test keys; fresh iframe geometry; bounded coordinate interaction; refresh recovery; parent-page postconditions; screenshots; and token-safe evidence.
---

# Test and operate Turnstile with drissionpage-mcp

Turnstile is a workflow composed from generic MCP tools. Keep provider-specific
selection, click offsets, retries, and callback interpretation in this Skill;
do not add a Turnstile-only tool to the MCP core. Use production targets only
when the operator is authorized to complete their challenge.

## Capability model

Turnstile normally renders in a cross-origin iframe from
`challenges.cloudflare.com`. That origin boundary does not determine the
available DrissionPage capability by itself:

- `frame_list` reports `boundary` and `document_access`. When
  `document_access=readable`, `frame_snapshot` and `frame_find` can inspect the
  OOPIF through the supported DrissionPage bridge.
- `document_access=outer_only` still supports outer iframe geometry and
  presentation evidence through `element_state_get`.
- Provider-managed Shadow DOM can make a top-level page script report zero
  iframes while DrissionPage selector lookup and `element_state_get` still find
  the widget. Treat that as a discovery-path difference, not proof that the
  widget is absent.
- `page_click_xy` consumes top-level viewport CSS coordinates. Only use a rect
  whose `viewport_coordinate_space` is `top_level_viewport`.

## Bounded procedure

1. Call `page_navigate`, resize if the fixture requires a fixed viewport, and
   wait for the parent page to report `pending`, `interactive`, `passed`, or
   `failed`. Record this pre-action status without recording the token value.
2. If the parent page already reports the expected terminal state, do not click.
   Official invisible keys require no checkbox action, and visible keys can
   settle before the observation window completes.
3. Discover the widget with `frame_list`. If it is not enumerated, use
   `wait_for_element` with a specific selector such as
   `iframe[src*='challenges.cloudflare.com']`.
4. Call `element_state_get` for the resolved iframe and inspect
   `rect.viewport_coordinate_space` plus
   `presentation.coordinate_actionability`.
   - `ready`: continue with the current viewport box.
   - `off_viewport`: call `element_scroll_into_view`, then use its `after`
     evidence or reacquire state.
   - `hidden`: keep waiting within the attempt deadline.
   - `covered` or `pointer_disabled`: wait for or operate the parent-page state
     that removes the obstruction, then reacquire state.
   - `transformed_3d`: wait for the animation or operate the page control that
     rotates/presents the widget face; click only after fresh evidence becomes
     actionable.
   - `target_document_only`: do not pass those coordinates to
     `page_click_xy`; reacquire the outer top-level iframe geometry.
5. For the standard 300x65 checkbox widget, click approximately 32 CSS pixels
   right and 32 CSS pixels down from `rect.viewport_location`. The component
   checkbox is not the iframe midpoint. Recalculate from the current rect for
   every attempt.
6. Wait for the parent-page callback or status element. A successful fixture
   may report `passed`; a negative official key must report `failed`. For a
   forced-interactive key, also require evidence that the interactive callback
   occurred.
7. Store only a boolean token-presence signal or token length. Never return,
   log, or persist the token value. Capture `page_screenshot` after the terminal
   postcondition for visual evidence.
8. On refresh, expiry, widget replacement, or layout change, start a new bounded
   attempt from discovery. Do not reuse a prior selector object or coordinate.

Example interaction branch:

```text
page_navigate
  -> wait for parent status
  -> frame_list or wait_for_element
  -> element_state_get
  -> element_scroll_into_view when off_viewport
  -> element_state_get after any layout change
  -> page_click_xy at viewport_location + (32, 32) when ready
  -> wait for parent callback/status
  -> page_screenshot
```

## Official Cloudflare test keys

Use Cloudflare's dummy keys for deterministic integration tests. Set widget
`retry` to `never` so the negative result remains observable.

| Sitekey | Configuration | Required terminal evidence |
| --- | --- | --- |
| `1x00000000000000000000AA` | Visible, always pass | `passed`; token present |
| `2x00000000000000000000AB` | Visible, always fail | `failed`; token absent |
| `1x00000000000000000000BB` | Invisible, always pass | `passed`; token present; zero checkbox clicks |
| `2x00000000000000000000BB` | Invisible, always fail | `failed`; token absent; zero checkbox clicks |
| `3x00000000000000000000FF` | Forced interactive | interactive callback observed, then `passed` |

The repository benchmark loads these keys only with explicit external-network
opt-in:

```bash
DP_HEADLESS=1 DP_NO_SANDBOX=1 DP_MCP_REQUIRE_BROWSER=1 \
python -m tests.evals.turnstile_testkey_benchmark \
  --iterations 10 --allow-external
```

Cloudflare references:

- https://developers.cloudflare.com/turnstile/troubleshooting/testing/
- https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/
- https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/widget-configurations/

## Production evidence contract

For an authorized production challenge, report the page and widget identifier,
attempt count, action type, actionability transitions, parent-page
postcondition, elapsed time, and final page state. A screenshot can supplement
the report. Never include a raw token, Cookie, credential, private destination,
or stale coordinate. A challenge is complete only when its parent-page
postcondition succeeds and the requested browser task can continue.

## Checklist

- [ ] Authorization and bounded attempt budget are explicit.
- [ ] The pre-action parent status was checked before clicking.
- [ ] Frame access was decided from `boundary` and `document_access`, not origin alone.
- [ ] The click rect uses `top_level_viewport` and current `ready` actionability.
- [ ] Off-viewport or transformed widgets were re-observed after the page changed.
- [ ] Visible interactive widgets use a component offset, not the iframe midpoint.
- [ ] Invisible keys receive no checkbox click.
- [ ] The terminal parent-page callback/status matches the expected case.
- [ ] Token evidence is limited to presence or length, followed by a screenshot.

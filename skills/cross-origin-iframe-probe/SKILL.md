---
name: cross-origin-iframe-probe
description: Use when a drissionpage-mcp task targets an iframe such as a payment widget, challenge, SSO flow, or embedded checkout. Classifies frame document access and outer presentation evidence, then selects a DOM, viewport-coordinate, scroll, keyboard, or parent-page verification path.
---

# Probe iframe boundaries with drissionpage-mcp

Use this Skill for an authorized iframe workflow. Cross-origin is a security
boundary, but it is not by itself proof that DrissionPage cannot inspect the
frame document. Make the decision from current capability evidence instead of
from the URL or origin alone.

## Decision procedure

1. Call `frame_list` and inspect each candidate's `boundary`,
   `document_access`, and `outer` evidence.
   - `boundary` is `same_origin`, `cross_origin`, or `unknown`.
   - `document_access=readable` means the current DrissionPage runtime can
     bridge the document. Use `frame_snapshot` or `frame_find` with the returned
     `index` or `selector`, including for a readable cross-origin OOPIF.
   - `document_access=outer_only` means frame DOM reads are unavailable. Keep
     the workflow on the iframe's outer element and parent page.
   - `unknown` is not success or failure. Confirm with the focused frame or
     element tools before choosing a path.
2. If `frame_list` does not enumerate the widget, use `element_find_all` with a
   specific iframe selector. Managed widgets may mount an iframe under a
   provider-owned Shadow DOM that top-level `document.querySelectorAll()` does
   not reveal even though DrissionPage selector lookup can resolve it.
3. Read `element_state_get` on the iframe selector. The returned geometry is
   for the outer iframe element. Preserve both coordinate-space labels:
   - `rect.coordinate_space=target_document` is the compatibility field.
   - Only `rect.viewport_coordinate_space=top_level_viewport` can be passed
     directly to `page_click_xy`, `page_pointer_move`, or `page_pointer_drag`.
   - `target_document_viewport` requires a higher-level coordinate conversion;
     do not treat it as a top-level click point.
4. Branch on `presentation.coordinate_actionability` before a coordinate
   action:
   - `ready`: compute the component-specific point from fresh
     `rect.viewport_location` evidence and continue.
   - `off_viewport`: call `element_scroll_into_view`, then use its `after`
     evidence or call `element_state_get` again.
   - `hidden`: wait for the widget to mount or become visible; do not click its
     zero or stale box.
   - `covered` or `pointer_disabled`: wait for the overlay/state transition or
     operate the page control that removes it, then re-observe.
   - `transformed_3d`: drive or wait for the page interaction that presents the
     target face, then re-read geometry. A static coordinate captured while the
     face is rotated is not actionable.
   - `target_document_only`: use a frame-scoped DOM action when readable, or
     obtain a top-level outer-frame point before coordinate input.
5. Use `element_scroll_into_view.before`, `after`, and `scroll_method` as the
   scroll receipt. Frame elements may use `page_fallback`; the action is usable
   when the `after` evidence is in the top-level viewport and reports the
   expected actionability.
6. For an `outer_only` widget with `ready` top-level geometry, use physical
   input through the browser pipeline:
   - `page_click_xy` for one fresh viewport point.
   - `page_pointer_move` or `page_pointer_drag` only when the interaction
     requires those gestures.
   - `keyboard_press` after a prior click establishes focus.
7. Verify from the parent page after every consequential action. Prefer a
   callback status, hidden-field presence or length, URL/title change, visible
   text, or another explicit element postcondition. Capture a screenshot as
   visual evidence, but do not expose a challenge token, Cookie, or credential.

## Retry discipline

Use a bounded attempt budget. Before each retry, reacquire the frame, check its
current `document_access`, re-read actionability and geometry, and verify that
the previous attempt did not already satisfy the parent-page postcondition.
Never replay stale coordinates after a refresh, layout shift, scroll, frame
replacement, transform, or tab change.

## Why this matters for atomic tools

`frame_*`, element, pointer, keyboard, wait, and screenshot tools deliberately
remain separate. The Skill owns the boundary decision and the observable
workflow postcondition; the MCP core supplies generic browser evidence and one
explicit action per call. This keeps production challenge, payment, SSO, and
embedded checkout procedures reusable without adding a provider-specific core
tool.

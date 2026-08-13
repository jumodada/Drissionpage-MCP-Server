---
name: cross-origin-iframe-probe
description: Use when a drissionpage-mcp task targets content inside an iframe (payment widgets, captchas, SSO popups, embedded checkouts) and element/frame tools start returning UNKNOWN_ERROR or ELEMENT_NOT_FOUND. Gives a decision procedure for same-origin vs cross-origin iframes and the fallback tool sequence for each case.
---

# Probing iframe content with drissionpage-mcp

## Decision procedure

1. Try `frame_list`. If it returns frames with non-zero `count`, they're
   enumerable (same-origin, or DrissionPage could bridge them) — use
   `frame_snapshot` / `frame_find` directly against `frame_index` or
   `frame_selector`.
2. If `frame_list` returns `count: 0` but `element_find_all` with
   `selector: "iframe"` still finds iframe elements, you're looking at a
   cross-origin iframe. DrissionPage can see the `<iframe>` tag and its
   attributes (`src`, size, position) but not cross into its document.
3. Confirm with `element_get_property` (`property: "src"`) — read-only outer
   metadata always works even when inner access doesn't.
4. Do NOT call `element_click`, `element_find`, `frame_find`, or
   `page_evaluate` expecting to read/act inside a cross-origin frame's DOM.
   `element_find`, `element_get_text`, and `element_state_get` have since
   been patched (this session) to degrade gracefully instead of throwing
   `UNKNOWN_ERROR` when the selector resolves to the `<iframe>` element
   itself — but they still can't reach content *inside* the frame's
   document, which remains a genuine cross-origin limitation, not a bug.
   `element_scroll_into_view` on a frame element has also been patched to
   fall back to scrolling the page to the frame's own location, since the
   frame's native `.scroll.to_see()` has an incompatible signature.
5. For interaction with cross-origin content, fall back to physical
   coordinate operations, which pass through the browser's real input
   pipeline instead of the DOM:
   - Compute a target point from the iframe's `rect` (position + size).
   - Use `page_click_xy` (and `page_pointer_move` / `page_pointer_drag` for
     more complex gestures) at that point.
   - Use `keyboard_press` for keyboard-driven flows once focus lands inside
     the frame from a prior click.
6. Verify effects from the outside: page-level hidden inputs, URL changes
   (`wait_for_url`), cookies (`browser_cookies_get`), or a screenshot — never
   assume you can read a success/failure state from inside the frame.
7. If a frame's `rect.viewport_location` never changes no matter how much
   you scroll or resize, check the page's CSS for `perspective` /
   `transform-style: preserve-3d` before assuming a tooling bug — a
   3D-transformed element can report `is_displayed: True` while its
   currently-rendered face is rotated away from the camera, which makes it
   genuinely unreachable by coordinate clicks regardless of any fix on the
   MCP side. See `turnstile-testing` for a concrete case of this on
   nowsecure.nl.

## Why this matters for atomic MCP tools generally

Atomic tools (`element_find`, `frame_find`, `page_evaluate`, ...) each assume
a DOM-reachable target. Cross-origin iframes are the sharpest edge case where
that assumption breaks silently with a generic `UNKNOWN_ERROR` rather than a
clear "this is cross-origin" message. When you hit that error on an iframe
boundary, stop retrying the same tool with different selectors — switch
register from DOM-based tools to coordinate/keyboard-based tools instead.

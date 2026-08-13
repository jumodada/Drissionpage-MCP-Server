---
name: turnstile-testing
description: Use when verifying that a Cloudflare Turnstile widget (or a page embedding one) can be solved through the drissionpage-mcp browser tools — covers Cloudflare's official test sitekeys (visible/invisible, always-pass/always-fail, forced-interactive-challenge), production sites like nowsecure.nl, and pages that wrap the widget in a CSS 3D transform. Includes the coordinate-click technique, how to compute click points from element_state_get, and the one scenario coordinate clicks genuinely cannot solve.
---

# Turnstile widget testing with drissionpage-mcp

## Why the "obvious" tools don't work here

Cloudflare Turnstile renders inside a cross-origin `<iframe>` from
`challenges.cloudflare.com`. DrissionPage represents that `<iframe>` as a
`ChromiumFrame` object, which has a much smaller surface than a normal
element — no `.text`, and its `.states`/`.rect` objects
(`FrameStates`/`FrameRect`) are missing most of the attributes a normal
element's states/rect expose (`is_covered`, `is_checked`, `midpoint`,
`click_point`, ...). Tools that assume every element has the full surface
throw `AttributeError`, which the MCP layer reports as an opaque
`UNKNOWN_ERROR`. As of this skill, `element_find`, `element_get_text`, and
`element_state_get` have been patched (see "Fixed upstream" below) to
degrade gracefully instead of crashing — but two things remain genuinely
impossible from outside the frame regardless of any fix:

- Reading/acting on content *inside* the iframe's document (its own DOM).
- `frame_list`/`frame_snapshot`/`frame_find` still return empty/error for
  cross-origin frames — that's a real limitation of cross-origin isolation,
  not a bug.

What you CAN always do: read the iframe's outer attributes
(`element_get_property` for `src`), get its outer box
(`element_state_get` for `rect`), and physically click a point on screen
(`page_click_xy`) — a real synthetic click crosses the origin boundary the
same way a human's cursor does.

## The technique

1. `page_navigate` to the target URL.
2. `wait_for_element` with `selector: "iframe"` (or a more specific selector
   if the page has several) — confirms the widget mounted, not that the
   challenge has rendered. Add 1-3s of `wait_time` after for the checkbox to
   paint.
3. `element_state_get` on the iframe selector. Read `rect.viewport_location`
   (not `location` — that's page-relative, and `page_click_xy` takes
   viewport-relative coordinates).
4. Compute the click point: the checkbox sits **~30px right, ~32px down**
   from the widget's top-left corner for the default 300x65 size — it is
   NOT at the widget's center (`midpoint`), don't use that.
5. `page_click_xy` at `viewport_location.x + 30`, `viewport_location.y + 32`.
6. `wait_time` ~2s for the challenge to resolve.
7. Verify success from outside the frame: `page_snapshot` or
   `page_evaluate` and check the hidden `input[name="cf-turnstile-response"]`
   has a non-empty value. A screenshot showing the checked box + "Success!"
   is good visual confirmation but the token is the reliable signal.

```
page_navigate      -> target URL
wait_for_element   -> selector: iframe, timeout: 10
element_state_get  -> selector: iframe            (read rect.viewport_location)
page_click_xy       -> x: loc.x + 30, y: loc.y + 32
wait_time          -> seconds: 2
page_snapshot      -> input[name="cf-turnstile-response"].value is non-empty  ✓ passed
```

## Verified against Cloudflare's official test sitekeys

Cloudflare documents dummy sitekeys with deterministic behavior, exactly for
this kind of automated testing (source: Cloudflare Turnstile docs,
"Test your Turnstile implementation"). All five were run through the
technique above:

| Sitekey | Behavior | Result |
|---|---|---|
| `1x00000000000000000000AA` | visible, always passes | Resolves on its own after the widget mounts — **no click needed**, just `wait_for_element` + a couple seconds of `wait_time`. |
| `2x00000000000000000000AB` | visible, always fails | Correctly stays `pending` / hidden input stays empty — confirms negative-case handling works, don't mistake this for a broken test. |
| `1x00000000000000000000BB` | invisible, always passes | No iframe checkbox to click at all; resolves purely by waiting. `element_find_all` still finds the (invisible) iframe in the DOM even though nothing is rendered. |
| `2x00000000000000000000BB` | invisible, always fails | Same as above, stays unresolved. |
| `3x00000000000000000000FF` | visible, **forces interactive challenge** | This is the one that needs the actual click. Confirmed via the coordinate-click technique above — this is also the sitekey seleniumbase.io/apps/turnstile uses. |

Swap the sitekey into a minimal test page
(`<div class="cf-turnstile" data-sitekey="...">`) plus
`<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer>`
to build a fast, deterministic local fixture instead of depending on a
public demo site's availability.

## Verified on a real production site: nowsecure.nl

[nowsecure.nl](https://nowsecure.nl/) is Cloudflare's own bot-detection demo
site and embeds Turnstile directly (using the same `3x00...FF` forced-challenge
key). Two widgets are present on the page. Results:

- **First widget** (normal document flow, no exotic CSS): solved reliably
  every run using the exact technique above — `element_state_get` →
  `viewport_location + (30, 32)` → `page_click_xy`.
- **Second widget**: embedded on the *back face of a live CSS 3D cube*
  (`transform-style: preserve-3d`, `perspective`, an infinite rotation
  animation, class names literally `cube` / `face front` / `face back`).
  Its DOM element exists and `element_find_all` sees it, but:
  - Its computed `rect.location` never enters the visible viewport — no
    amount of `page_scroll`/`page_resize` fixes this, because the element
    simply isn't part of the page's normal scrollable flow; it's positioned
    by the 3D transform. Cloudflare's own bounding-box-based
    `is_displayed` state reports `True` even though the face is rotated away
    from the camera and isn't actually visible.
  - **This is the one case coordinate-click cannot solve.** Don't burn
    retries trying to scroll/resize your way to it — check for
    `perspective`/`transform-style: preserve-3d` in the page's CSS (or just
    notice a widget's `rect.viewport_location` never moves no matter what
    you do) and treat it as out of reach for this technique. If the task
    genuinely requires solving it, that needs either waiting for the cube's
    own animation to rotate the target face toward the camera (fragile,
    timing-dependent) or driving the interaction that specifically triggers
    the front/back swap, not blind coordinate clicking.

## Fixed upstream (this session)

Three real bugs were found and patched while building this skill — all were
"assumes every element has the same shape" bugs triggered specifically by
`ChromiumFrame` objects (cross-origin iframes):

1. `elements.py` `find()` / `text()` read `element.text` unconditionally →
   `AttributeError` on frames. Fixed with `hasattr` guards.
2. `elements.py` `state()` read `states.is_covered`, `rect.midpoint`,
   `rect.click_point`, etc. unconditionally → `AttributeError` on frames
   (`FrameStates`/`FrameRect` only expose a handful of attributes). Fixed
   with `getattr` defaults for state flags, and a location+size-derived
   fallback for midpoint/click_point so `element_state_get` on an iframe now
   returns a usable `click_point` even though the native attribute doesn't
   exist.
3. `interaction.py` `scroll_element_into_view()` called
   `element.scroll.to_see(center=center)` unconditionally → `TypeError` on
   frames, because `ChromiumFrame.scroll` is a `FrameScroller` whose
   `to_see()` requires a `loc_or_ele` positional argument rather than
   accepting `center` alone (and passing the frame itself as `loc_or_ele`
   also fails, with a `JavaScriptError`, since the underlying JS assumes a
   normal DOM `this`). Fixed by catching the `TypeError` and falling back to
   `page.scroll.to_location(*frame.rect.location)` — scrolling the page's
   own viewport to the frame's location instead of asking the frame to
   scroll itself into view.

Regression tests: `tests/test_frame_element_state.py`,
`tests/test_frame_scroll_into_view.py`.

## Reusable checklist

- [ ] Never expect `element_click`/`frame_find`/`frame_snapshot` to work on the Turnstile iframe directly — cross-origin, always fails or returns empty.
- [ ] Use `element_get_property` (`src`) only to confirm the widget mounted.
- [ ] Use `element_state_get` → `rect.viewport_location`, not `element_get_html`/guessed pixels, to compute the click point precisely.
- [ ] Click ~30px right / ~32px down from the widget's top-left corner — NOT the midpoint.
- [ ] Confirm success via the page-level hidden `cf-turnstile-response` input, not by trying to read inside the iframe.
- [ ] "always-pass"/"invisible" sitekeys need no click at all — don't click reflexively, check if it already resolved after a short wait first.
- [ ] If a widget's `rect.viewport_location` never changes no matter how you scroll/resize, check the page CSS for `perspective`/`transform-style: preserve-3d` before assuming it's a positioning bug on your end — it may be a 3D-transformed element genuinely out of reach for coordinate clicks.

# DrissionPage MCP Lab

`playground/` is now a deterministic MCP Lab instead of a collection of stale demo scripts. It provides a local business test site plus a stdio MCP runner so you can verify how real agents use DrissionPage MCP.

The lab is inspired by complex DrissionPage fixture-site ideas, but it is implemented specifically for this MCP server and does not depend on external sites or the `ssr-site` source tree.

## What it covers

- `registry` — real stdio MCP initialize/list/call smoke without opening a browser.
- `site` — no-browser local HTTP fixture smoke.
- `form-inspect` — real browser `form_inspect` flow with password value masking.
- `commerce` — Taobao-like product search/cards/cart-oriented page understanding.
- `social-notes` — Xiaohongshu-like mobile feed, note cards, search form, and detail links.
- `timeline` — Twitter-like composer, timeline posts, dynamic load-more behavior.

## Quick start

No browser required:

```bash
python playground/run_mcp_lab.py --case site
python playground/run_mcp_lab.py --case registry
```

Browser-backed checks:

```bash
DP_HEADLESS=1 python playground/run_mcp_lab.py --case form-inspect
DP_HEADLESS=1 python playground/run_mcp_lab.py --case commerce
DP_HEADLESS=1 python playground/run_mcp_lab.py --case social-notes
DP_HEADLESS=1 python playground/run_mcp_lab.py --case timeline
```

Run everything and get machine-readable output:

```bash
DP_HEADLESS=1 python playground/run_mcp_lab.py --all --json
```

If Chrome/Chromium is unavailable but you still want no-browser cases to pass:

```bash
python playground/run_mcp_lab.py --all --skip-browser-if-unavailable
```

## Local site routes

The lab starts a deterministic local HTTP server on `127.0.0.1` during each case.

| Route | Purpose |
| --- | --- |
| `/` | MCP Lab index. |
| `/cases/forms` | Form controls, select options, readonly textarea, checkbox, and password field. |
| `/scenarios/commerce` | Commerce home with search form and product cards. |
| `/scenarios/commerce/search?q=耳机` | Commerce search result page. |
| `/scenarios/commerce/item/aurora-headphones` | Product detail with SKU form. |
| `/scenarios/commerce/cart` | Cart summary. |
| `/scenarios/commerce/checkout` | Checkout form. |
| `/scenarios/social-notes` | Mobile social notes feed. |
| `/scenarios/social-notes/note/note-002` | Note detail and comment form. |
| `/scenarios/social-notes/security-check` | Synthetic safety landing. |
| `/scenarios/timeline` | Timeline composer, posts, and dynamic load-more. |
| `/api/manifest.json` | Machine-readable site manifest. |

## Why this exists

The old playground only loaded tools or pointed people to public demo sites. This lab tests the real contract that matters for MCP clients:

1. Can the client discover the current 22-tool registry?
2. Can it navigate a deterministic local business page?
3. Can `page_snapshot` expose high-value controls on dense pages?
4. Can `element_find_all` extract repeated cards/posts?
5. Can `form_inspect` inspect realistic forms without leaking password values?
6. Can dynamic UI changes be verified through MCP tools instead of screenshots alone?

## CI usage

Use lightweight no-browser cases in generic CI:

```bash
python playground/run_mcp_lab.py --case registry --json
python playground/run_mcp_lab.py --case site --json
```

Use browser-backed cases in browser jobs or release checks:

```bash
DP_HEADLESS=1 DP_NO_SANDBOX=1 python playground/run_mcp_lab.py --case form-inspect --json
```

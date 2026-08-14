---
name: xiaohongshu-content-research
description: Use for authorized, read-only research on public Xiaohongshu content or the local Xiaohongshu-like playground fixture. Enforces robots, login, captcha, rate-limit, and safety checks before collecting bounded note metadata.
---

# Xiaohongshu content research

This Skill composes the generic `drissionpage-mcp` tools for content research.
The MCP host executes the tool calls; the Markdown Skill itself does not access
the browser or network. It does not log in, bypass a captcha, defeat a safety
page, or submit likes, comments, follows, messages, or purchases. Use it only
for content that the operator is authorized to inspect.

## Stop conditions

Stop before navigation when the target is not authorized or its robots policy
does not permit the requested access. Stop when the site requests login,
verification, captcha interaction, or an anti-bot challenge that is not an
explicitly authorized test fixture. Do not retry a safety page or rotate
identities, proxies, headers, or user agents to evade a restriction.

The public Xiaohongshu site may return a safety restriction page or error code
300012. Treat that as a product boundary, not as a selector or timeout bug.
Use the local `social-notes` playground case for deterministic integration
tests without contacting Xiaohongshu.

## Bounded read-only sequence

1. Confirm the URL, authorization, robots policy, and a small request budget.
2. Call `page_navigate` once, then `page_observe` or `page_snapshot`.
3. If a search form is visibly available, use `element_find` and
   `element_type`; verify the input value with `element_get_property` before
   one explicit submit click. Do not submit more than the operator requested.
4. Use `element_find_all` for note cards and extract only bounded visible
   fields such as title, author label, link, and visible text excerpt.
5. Open at most the requested number of detail links with `page_navigate` or
   `new_tab=true`. Re-observe each page before reading it.
6. Verify each result with `element_get_text`, `element_get_attribute`, or
   `page_snapshot`. Record missing, gated, or truncated fields as unknown.
7. Close additional tabs and return a source URL, collection count, and the
   exact stop reason for any skipped item.

## Local playground validation

Run the deterministic fixture from the repository root:

```bash
DP_HEADLESS=1 python playground/run_mcp_lab.py --case social-notes --json
```

The fixture validates a mobile feed, three note cards, a search control, and a
detail route without public-site traffic. For MCP client testing, start the
server from a built release package and pass its interpreter with `--command`.

## Evidence and privacy

Keep collection bounded and avoid passwords, cookies, storage values, private
messages, phone numbers, or other personal data. Do not place raw private
content in logs or generated reports. Prefer title/author/link/excerpt fields,
state the timestamp and URL, and preserve uncertainty when content is hidden or
changed between observations.

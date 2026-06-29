# DrissionPage MCP Skills Notes

This directory is a repository-local skills document set. It captures the practical lessons from the 0.4.x stabilization work so future agents can repeat the same quality bar without rediscovering the same issues.

These are documentation skills, not installed Codex skills. Keep them in the repo unless you intentionally promote one into `.codex/skills`.

## Skill documents

- [Coverage Quality](coverage-quality/SKILL.md) — how to raise coverage with real MCP/browser behavior instead of line-count padding.
- [MCP Client Docs](mcp-client-docs/SKILL.md) — how to maintain README guidance for Codex, Claude Code, Cursor, and Claude Desktop after the `examples/` directory removal.
- [Release Metadata](release-metadata/SKILL.md) — release/version/tag/badge checks and common PyPI/GitHub cache pitfalls.
- [MCP Error Contracts](mcp-error-contracts/SKILL.md) — structured error semantics, selector normalization, and compatibility-surface policy.

## Current quality baseline

- Coverage gate: `fail_under = 95`.
- Recent verified coverage: about `98.9%` with browser integration enabled in CI.
- CI coverage job installs Chromium and sets `DP_MCP_REQUIRE_BROWSER=1`; browser integration failures should not silently skip there.
- Public package should expose only the canonical `drissionpage_mcp` package.
- `examples/` has been removed. Do not reintroduce tests or MANIFEST rules that require it.

## Default verification stack

```bash
python -m ruff check drissionpage_mcp tests playground
python -m mypy drissionpage_mcp
python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml:coverage.xml -q
DP_MCP_REQUIRE_BROWSER=1 python -m pytest tests/test_browser_integration.py -q
git diff --check
```

## Collaboration note

Do not commit or push unless the maintainer explicitly asks. Keep worktree changes reviewable and report changed files plus validation evidence.

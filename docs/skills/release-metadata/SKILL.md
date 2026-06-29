---
name: drissionpage-mcp-release-metadata
description: Prepare and verify DrissionPage MCP release metadata, badges, tags, package contents, and CI coverage behavior.
---

# Release Metadata Skill

Use this before a release or when PyPI/GitHub metadata looks wrong.

## Version surfaces

Keep these aligned:

- `pyproject.toml` project version
- `drissionpage_mcp/__init__.py` `__version__`
- README / README_CN visible version text
- `CHANGELOG.md`
- release metadata tests
- git tag target

## Tag correction

If a release tag points to the wrong commit and the maintainer explicitly asks to move it:

```bash
git tag -f vX.Y.Z <correct-commit>
git push origin refs/tags/vX.Y.Z --force
```

Then verify:

```bash
git rev-parse vX.Y.Z^{commit}
git ls-remote --tags origin refs/tags/vX.Y.Z
```

## Package contents

The wheel must expose only the canonical top-level package:

```text
drissionpage_mcp
```

Do not publish a broad top-level `src` package or deleted `examples/` assets.

## README badges

Prefer Shields for PyPI version badges:

```md
https://img.shields.io/pypi/v/drissionpage-mcp.svg?cacheSeconds=3600
```

Avoid Badge Fury for current-version badges because it can cache for days. GitHub also proxies images through `camo.githubusercontent.com`; changing the badge URL query can force a new cache key.

## PyPI and mirrors

If PyPI has the new version but a badge or mirror still looks old:

1. Check PyPI JSON directly.
2. Check the direct Shields badge.
3. Check GitHub camo cache if README rendering is stale.
4. Treat package mirrors and download dashboards as eventually consistent.

## CI coverage

Coverage is expected to run with browser integration in the coverage job:

- install Chromium
- set `CHROME_PATH`
- set `DP_HEADLESS=1`
- set `DP_NO_SANDBOX=1`
- set `DP_MCP_REQUIRE_BROWSER=1`

This prevents browser-backed tests from silently skipping in the coverage gate.

## Verification stack

```bash
python -m ruff check drissionpage_mcp tests playground
python -m mypy drissionpage_mcp
python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml:coverage.xml -q
python -m build
python -m twine check dist/*
```

For releases, inspect wheel contents before upload.

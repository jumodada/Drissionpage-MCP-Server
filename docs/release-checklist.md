# Release Checklist

Use this checklist before publishing a DrissionPage MCP release.

## 1. Version and Metadata

- [ ] Update `drissionpage_mcp/__init__.py` version.
- [ ] Update `pyproject.toml` version.
- [ ] Update `CHANGELOG.md` with user-visible changes.
- [ ] Confirm supported Python and DrissionPage ranges in [compatibility.md](compatibility.md).
- [ ] Confirm `drissionpage-mcp --version`, `drissionpage_mcp.__version__`, `importlib.metadata.version("drissionpage-mcp")`, `pyproject.toml`, and built wheel metadata agree.

## 2. Local Validation

Run from a clean checkout:

```bash
python -m pip install -e ".[dev]"
python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))"
python -m pytest tests/
python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml:coverage.xml
python -m ruff check drissionpage_mcp tests playground
python -m build
python -m twine check dist/*
```

Notes:

- On Python 3.10, use `python -c "import tomli; tomli.load(open('pyproject.toml', 'rb'))"` after installing development dependencies; Python 3.11+ can use stdlib `tomllib`.
- Remove or archive stale `dist/` files before building a final release artifact.
- Confirm `coverage.xml` is generated and the GitHub repository has `CODECOV_TOKEN` configured for the Codecov upload job.
- Confirm CI still runs the package job step named `Check wheel package contents` so the wheel exposes only `drissionpage_mcp`.

## 3. Browser Smoke Test

With Chrome or Chromium installed, run at least one browser-backed smoke test:

```bash
python playground/quick_start.py
python -c "from DrissionPage import Chromium; b = Chromium(); print(b.latest_tab.url); b.quit()"
```

If the smoke test cannot run in the release environment, document the gap in the release notes.

## 4. Documentation

- [ ] README quick start matches the released package name, version, and Codex/JSON MCP setup.
- [ ] MCP client config snippets in the README are valid JSON/TOML, including the Codex `config.toml` block.
- [ ] Troubleshooting steps still match current CLI behavior.
- [ ] Tool inventory matches the registered tools.
- [ ] Resource and prompt inventories match MCP `resources/list` and `prompts/list`.
- [ ] `python -m pytest tests/evals -q` passes or browser-required evals skip with explicit local-browser diagnostics.

## 5. Publish

```bash
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

After publish:

- [ ] Install from PyPI in a fresh environment.
- [ ] Run `drissionpage-mcp --version`.
- [ ] Create a GitHub release with changelog highlights.

# Contributing

Thank you for improving DrissionPage MCP. Keep changes small, tested, and focused on the MCP server, browser compatibility, or documentation.

## Development Setup

```bash
git clone https://github.com/jumodada/DrissionMCP.git
cd DrissionMCP
python -m pip install -e ".[dev]"
python playground/quick_start.py
```

`playground/quick_start.py` checks that the package imports and the tool registry loads.

## Before Opening a Pull Request

Run the checks that match your change:

```bash
python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"
python -m pytest tests/
python -m ruff check drissionpage_mcp tests playground
python -m build
python -m twine check dist/*
```

Browser-backed changes should also be tested with a local Chrome or Chromium install.

## Contribution Guidelines

- Do not remove or rename public MCP tools without documenting a deprecation path.
- Keep tool schemas backward compatible when practical.
- Add or update tests for changed behavior.
- Keep README changes concise and link detailed docs from `docs/`.
- Do not commit generated files such as `dist/`, `*.egg-info/`, caches, screenshots, or local IDE state.

## Pull Request Checklist

- [ ] The PR explains the user-visible change.
- [ ] Tests or validation commands are listed.
- [ ] Documentation is updated when behavior or setup changes.
- [ ] Browser compatibility impact is noted when relevant.

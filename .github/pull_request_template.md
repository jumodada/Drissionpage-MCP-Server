## Summary

- 

## Validation

- [ ] `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`
- [ ] `python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml`
- [ ] `python -m ruff check drissionpage_mcp tests playground`
- [ ] `python -m build && python -m twine check dist/*`
- [ ] Browser smoke test, if browser behavior changed

## Compatibility

- [ ] Public tool names and schemas remain backward compatible, or deprecation is documented.
- [ ] README/docs updated for user-visible behavior changes.

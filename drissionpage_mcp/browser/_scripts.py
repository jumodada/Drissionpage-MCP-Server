"""Internal helpers for browser-side JavaScript execution."""

from typing import Any


def run_structured_script(page: Any, script: str, error_message: str) -> dict[str, Any]:
    """Run JavaScript and require an object-shaped result."""

    result = page.run_js(script, as_expr=True)
    if not isinstance(result, dict):
        raise RuntimeError(error_message)
    return result

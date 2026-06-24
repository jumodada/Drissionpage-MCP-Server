"""Backward-compatible CLI shim. Prefer ``python -m drissionpage_mcp.cli``."""

from drissionpage_mcp.cli import main, main_async

if __name__ == "__main__":
    main()

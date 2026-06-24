"""Doctor/self-test diagnostics for drissionpage-mcp."""

import importlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from typing import Any, Dict, List, Optional

from . import __version__


def _package_version(module_name: str, version_attr: str = "__version__") -> str:
    """Return importable package version using metadata before module attrs."""

    distribution_names = {
        "mcp": "mcp",
        "DrissionPage": "DrissionPage",
    }
    try:
        return importlib.metadata.version(
            distribution_names.get(module_name, module_name)
        )
    except importlib.metadata.PackageNotFoundError:
        pass

    try:
        module = importlib.import_module(module_name)
        return str(getattr(module, version_attr, "unknown"))
    except Exception as exc:
        return "unavailable: %s" % exc


def _find_browser() -> Optional[str]:
    candidates = [
        os.getenv("CHROME_PATH"),
        os.getenv("DP_BROWSER_PATH"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
    ]
    if sys.platform == "darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _config() -> Dict[str, Any]:
    names = [
        "CHROME_PATH",
        "DP_BROWSER_PATH",
        "DP_USER_DATA_PATH",
        "DP_AUTO_PORT",
        "DP_HEADLESS",
        "DP_LOAD_MODE",
        "DP_TIMEOUT",
        "DP_PAGE_LOAD_TIMEOUT",
        "DP_SCRIPT_TIMEOUT",
        "DP_NO_SANDBOX",
        "DP_DISABLE_WEB_SECURITY",
    ]
    return {name: os.getenv(name) for name in names if os.getenv(name) is not None}


def run_diagnostics(launch_browser: bool = False) -> Dict[str, Any]:
    """Collect package/config/browser diagnostics without launching by default."""

    checks: List[Dict[str, Any]] = []
    hints: List[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    python_ok = sys.version_info >= (3, 10)
    check("python", python_ok, sys.version.split()[0])
    if not python_ok:
        hints.append("Use Python 3.10 or newer.")

    mcp_version = _package_version("mcp")
    check("mcp_package", not mcp_version.startswith("unavailable"), mcp_version)

    dp_version = _package_version("DrissionPage")
    check("drissionpage_package", not dp_version.startswith("unavailable"), dp_version)

    browser_path = _find_browser()
    check(
        "browser_binary",
        bool(browser_path),
        browser_path or "not found on PATH/default locations",
    )
    if not browser_path:
        hints.append("Install Chrome/Chromium or set CHROME_PATH/DP_BROWSER_PATH.")

    config = _config()
    check(
        "config",
        True,
        json.dumps(config, sort_keys=True) if config else "default environment",
    )

    launch_detail = "skipped (pass --launch-browser to test browser startup)"
    launch_ok = True
    if launch_browser:
        try:
            from .compat import create_browser, quit_browser

            browser = create_browser()
            try:
                launch_detail = "launched successfully"
            finally:
                quit_browser(browser)
        except Exception as exc:
            launch_ok = False
            launch_detail = "%s: %s" % (exc.__class__.__name__, exc)
            hints.append(
                "Browser launch failed. Check CHROME_PATH/DP_BROWSER_PATH, sandbox permissions, and headless settings."
            )
    check("browser_launch", launch_ok, launch_detail)

    ok = all(item["ok"] for item in checks)
    return {
        "ok": ok,
        "version": __version__,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_executable": sys.executable,
        },
        "checks": checks,
        "hints": hints,
    }


def format_diagnostics(report: Dict[str, Any]) -> str:
    """Format diagnostics for humans while preserving JSON parseability."""

    lines = [
        "DrissionPage MCP doctor",
        "status: %s" % ("ok" if report.get("ok") else "problem"),
        "version: %s" % report.get("version", "unknown"),
    ]
    platform_info = report.get("platform", {})
    lines.append(
        "platform: {system} {release} {machine} ({python_executable})".format(
            system=platform_info.get("system", "unknown"),
            release=platform_info.get("release", ""),
            machine=platform_info.get("machine", ""),
            python_executable=platform_info.get("python_executable", ""),
        )
    )
    lines.append("checks:")
    for item in report.get("checks", []):
        mark = "ok" if item.get("ok") else "fail"
        lines.append(
            "  - [%s] %s: %s" % (mark, item.get("name"), item.get("detail", ""))
        )
    if report.get("hints"):
        lines.append("hints:")
        for hint in report["hints"]:
            lines.append("  - %s" % hint)
    lines.append("### JSON_RESULT")
    lines.append("```json")
    lines.append(json.dumps(report, ensure_ascii=False, sort_keys=True))
    lines.append("```")
    return "\n".join(lines)

#!/usr/bin/env python3
"""Validate repository Skills against the versioned MCP catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from drissionpage_mcp.resources import SKILL_EXAMPLES, SKILLS_SOURCE_REVISION
from drissionpage_mcp.tools import get_all_tools

ROOT = Path(__file__).resolve().parents[1]
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing YAML frontmatter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("unterminated YAML frontmatter") from exc

    values: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) or ":" not in line:
            raise ValueError("frontmatter must contain flat key/value pairs")
        key, value = line.split(":", 1)
        key = key.strip()
        if key in values:
            raise ValueError(f"duplicate frontmatter field: {key}")
        values[key] = value.strip()
    return values


def validate_skills(root: Path = ROOT) -> dict[str, Any]:
    """Return a deterministic report for all catalogued repository Skills."""

    tool_names = {tool.name for tool in get_all_tools()}
    results: list[dict[str, Any]] = []
    for catalog_entry in SKILL_EXAMPLES:
        name = str(catalog_entry["name"])
        path = root / str(catalog_entry["path"])
        errors: list[str] = []
        text = ""

        if not path.is_file():
            errors.append("skill entrypoint is missing")
        else:
            text = path.read_text(encoding="utf-8")
            try:
                metadata = _frontmatter(text)
            except ValueError as exc:
                errors.append(str(exc))
            else:
                if set(metadata) != {"name", "description"}:
                    errors.append("frontmatter must contain only name and description")
                if metadata.get("name") != name:
                    errors.append("frontmatter name does not match catalog")
                if not NAME_PATTERN.fullmatch(metadata.get("name", "")):
                    errors.append("skill name is not lowercase hyphen-case")
                description = metadata.get("description", "")
                if not description or len(description) > 1024:
                    errors.append("description must contain 1-1024 characters")

            if len(text.splitlines()) >= 500:
                errors.append("SKILL.md must stay under 500 lines")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != catalog_entry["sha256"]:
                errors.append("SHA-256 does not match catalog")

        required_tools = set(catalog_entry["required_tools"])
        unknown_tools = sorted(required_tools - tool_names)
        if unknown_tools:
            errors.append("unknown required tools: " + ", ".join(unknown_tools))
        if catalog_entry["source_revision"] != SKILLS_SOURCE_REVISION:
            errors.append("source revision does not match catalog release")
        source_url = str(catalog_entry["source_url"])
        if f"/tree/{SKILLS_SOURCE_REVISION}/" not in source_url:
            errors.append("source URL is not pinned to the catalog revision")

        results.append(
            {
                "name": name,
                "ok": not errors,
                "path": str(catalog_entry["path"]),
                "required_tools": sorted(required_tools),
                "errors": errors,
            }
        )

    return {
        "ok": all(item["ok"] for item in results),
        "source_revision": SKILLS_SOURCE_REVISION,
        "tool_count": len(tool_names),
        "skills": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()
    report = validate_skills()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        for item in report["skills"]:
            status = "PASS" if item["ok"] else "FAIL"
            print(f"[{status}] {item['name']}")
            for error in item["errors"]:
                print(f"  - {error}")
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

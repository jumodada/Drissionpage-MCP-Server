"""Static discovery metadata for optional external Skills."""

from __future__ import annotations

import json

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource
from pydantic import AnyUrl

from . import __version__

SKILLS_CATALOG_URI = "drissionpage://skills/catalog"
SKILLS_CATALOG_URL = "https://github.com/jumodada/skills-manager"
RESOURCE_JSON_MAX_CHARS = 4000


def list_resources() -> list[Resource]:
    """Expose the single optional-Skills discovery resource."""

    return [
        Resource(
            uri=AnyUrl(SKILLS_CATALOG_URI),
            name="skills_catalog",
            title="Optional Skills Catalog",
            description=(
                "Discovery metadata for optional Skills published separately from "
                "the standalone MCP server."
            ),
            mimeType="application/json",
        )
    ]


def read_resource(uri: str) -> list[ReadResourceContents]:
    """Return bounded static metadata without browser or network access."""

    if uri.rstrip("/") != SKILLS_CATALOG_URI:
        raise ValueError(f"Unknown resource URI: {uri}")
    payload = {
        "schema_version": "1",
        "mcp_version": __version__,
        "optional": True,
        "catalog_url": SKILLS_CATALOG_URL,
        "catalog_path": "skills/",
        "skill_entrypoint": "skills/<skill-name>/SKILL.md",
        "status": "unpublished",
        "skills": [],
    }
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(content) > RESOURCE_JSON_MAX_CHARS:
        raise ValueError("Skills catalog exceeds the resource size limit")
    return [ReadResourceContents(content=content, mime_type="application/json")]


__all__ = [
    "RESOURCE_JSON_MAX_CHARS",
    "SKILLS_CATALOG_URI",
    "SKILLS_CATALOG_URL",
    "list_resources",
    "read_resource",
]

"""Static discovery metadata for optional external Skills."""

from __future__ import annotations

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource
from pydantic import AnyUrl

from . import __version__
from .response_json import strict_json_dumps

SKILLS_CATALOG_URI = "drissionpage://skills/catalog"
SKILLS_CATALOG_URL = "https://github.com/jumodada/skills-manager"
SKILLS_REPOSITORY_URL = "https://github.com/jumodada/Drissionpage-MCP-Server"
RESOURCE_JSON_MAX_CHARS = 4000

SKILL_EXAMPLES = (
    {
        "name": "cross-origin-iframe-probe",
        "description": "Diagnose iframe boundaries and choose DOM, coordinate, or keyboard fallbacks.",
        "path": "skills/cross-origin-iframe-probe/SKILL.md",
        "source_url": f"{SKILLS_REPOSITORY_URL}/tree/main/skills/cross-origin-iframe-probe",
        "status": "repository_example",
    },
    {
        "name": "turnstile-testing",
        "description": "Test authorized Turnstile fixtures and verify cross-origin widget outcomes from the parent page.",
        "path": "skills/turnstile-testing/SKILL.md",
        "source_url": f"{SKILLS_REPOSITORY_URL}/tree/main/skills/turnstile-testing",
        "status": "repository_example",
    },
    {
        "name": "xiaohongshu-content-research",
        "description": "Run bounded, read-only Xiaohongshu-like content research with explicit robots, login, and rate-limit checks.",
        "path": "skills/xiaohongshu-content-research/SKILL.md",
        "source_url": f"{SKILLS_REPOSITORY_URL}/tree/main/skills/xiaohongshu-content-research",
        "status": "repository_example",
    },
)


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
        "repository_url": SKILLS_REPOSITORY_URL,
        "catalog_path": "skills/",
        "skill_entrypoint": "skills/<skill-name>/SKILL.md",
        "status": "repository_examples",
        "skills": list(SKILL_EXAMPLES),
    }
    content = strict_json_dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(content) > RESOURCE_JSON_MAX_CHARS:
        raise ValueError("Skills catalog exceeds the resource size limit")
    return [ReadResourceContents(content=content, mime_type="application/json")]


__all__ = [
    "RESOURCE_JSON_MAX_CHARS",
    "SKILLS_CATALOG_URI",
    "SKILLS_CATALOG_URL",
    "SKILLS_REPOSITORY_URL",
    "SKILL_EXAMPLES",
    "list_resources",
    "read_resource",
]

"""Static discovery metadata for optional external Skills."""

from __future__ import annotations

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource
from pydantic import AnyUrl

from . import __version__
from .response_json import strict_json_dumps

SKILLS_CATALOG_URI = "drissionpage://skills/catalog"
SKILLS_CATALOG_URL = "https://github.com/jumodada/skills-manager"
SKILLS_REPOSITORY_URL = SKILLS_CATALOG_URL
SKILLS_SOURCE_REVISION = "v0.8.3"
RESOURCE_JSON_MAX_CHARS = 8192

SKILL_EXAMPLES = (
    {
        "name": "cross-origin-iframe-probe",
        "description": "Diagnose iframe boundaries and choose DOM, coordinate, or keyboard fallbacks.",
        "skill_version": "0.1.0",
        "mcp_compatibility": ">=0.8.2,<0.9.0",
        "required_tools": [
            "frame_list",
            "frame_snapshot",
            "frame_find",
            "element_find_all",
            "element_get_property",
            "element_state_get",
            "page_click_xy",
            "page_pointer_move",
            "page_pointer_drag",
            "keyboard_press",
            "wait_for_url",
        ],
        "fixture": "document-boundaries",
        "path": "skills/cross-origin-iframe-probe/SKILL.md",
        "source_revision": SKILLS_SOURCE_REVISION,
        "source_url": f"{SKILLS_REPOSITORY_URL}/tree/{SKILLS_SOURCE_REVISION}/skills/cross-origin-iframe-probe",
        "sha256": "740a12605f7153d75784962c0bee2340627e9e6274d29e15f6ee24df9f8b6a49",
        "verification_status": "fixture_verified",
        "status": "repository_example",
    },
    {
        "name": "turnstile-testing",
        "description": "Operate Turnstile test fixtures and authorized production challenges with geometry and parent-page verification.",
        "skill_version": "0.1.0",
        "mcp_compatibility": ">=0.8.2,<0.9.0",
        "required_tools": [
            "page_navigate",
            "wait_for_element",
            "element_find_all",
            "element_get_property",
            "element_state_get",
            "page_click_xy",
            "page_evaluate",
            "page_snapshot",
            "page_scroll",
            "page_resize",
            "wait_time",
        ],
        "fixture": "cloudflare-test-sitekeys",
        "path": "skills/turnstile-testing/SKILL.md",
        "source_revision": SKILLS_SOURCE_REVISION,
        "source_url": f"{SKILLS_REPOSITORY_URL}/tree/{SKILLS_SOURCE_REVISION}/skills/turnstile-testing",
        "sha256": "097e02a3884a7cdb34ddb4c2d472507bd990b1915a01187f3eef697c2a1c5368",
        "verification_status": "field_evaluated",
        "status": "repository_example",
    },
    {
        "name": "xiaohongshu-content-research",
        "description": "Run bounded, read-only Xiaohongshu-like content research with explicit robots, login, and rate-limit checks.",
        "skill_version": "0.1.0",
        "mcp_compatibility": ">=0.8.2,<0.9.0",
        "required_tools": [
            "page_navigate",
            "page_observe",
            "page_snapshot",
            "element_find",
            "element_type",
            "element_get_property",
            "element_find_all",
            "element_get_text",
            "element_get_attribute",
            "tab_close",
        ],
        "fixture": "social-notes",
        "path": "skills/xiaohongshu-content-research/SKILL.md",
        "source_revision": SKILLS_SOURCE_REVISION,
        "source_url": f"{SKILLS_REPOSITORY_URL}/tree/{SKILLS_SOURCE_REVISION}/skills/xiaohongshu-content-research",
        "sha256": "471491b89c1720df2357fc56f5db51e9af08d1812a5c097d58d6d5e59efad331",
        "verification_status": "fixture_verified",
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
        "schema_version": "2",
        "mcp_version": __version__,
        "optional": True,
        "catalog_url": SKILLS_CATALOG_URL,
        "repository_url": SKILLS_REPOSITORY_URL,
        "source_revision": SKILLS_SOURCE_REVISION,
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
    "SKILLS_SOURCE_REVISION",
    "SKILL_EXAMPLES",
    "list_resources",
    "read_resource",
]

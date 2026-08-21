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
SKILLS_SOURCE_REVISION = "v0.8.4"
RESOURCE_JSON_MAX_CHARS = 8192

SKILL_EXAMPLES = (
    {
        "name": "cross-origin-iframe-probe",
        "description": "Classify frame access and choose DOM, outer geometry, pointer, keyboard, or parent-page paths.",
        "skill_version": "0.2.0",
        "mcp_compatibility": ">=0.8.4,<0.9.0",
        "required_tools": [
            "frame_list",
            "frame_snapshot",
            "frame_find",
            "element_find_all",
            "element_state_get",
            "element_scroll_into_view",
            "element_get_property",
            "element_get_text",
            "page_click_xy",
            "page_pointer_move",
            "page_pointer_drag",
            "keyboard_press",
            "wait_until",
            "wait_for_url",
            "page_screenshot",
        ],
        "fixture": "document-boundaries",
        "path": "skills/cross-origin-iframe-probe/SKILL.md",
        "source_revision": SKILLS_SOURCE_REVISION,
        "source_url": f"{SKILLS_REPOSITORY_URL}/tree/{SKILLS_SOURCE_REVISION}/skills/cross-origin-iframe-probe",
        "sha256": "d36e34e1a9e1de1660a6d6efeec2bf7aa36367ca112ffdc88a3f9f81f0ebd21c",
        "verification_status": "fixture_verified",
        "status": "repository_example",
    },
    {
        "name": "turnstile-testing",
        "description": "Operate authorized Turnstile fixtures and production challenges with fresh geometry and token-safe verification.",
        "skill_version": "0.2.0",
        "mcp_compatibility": ">=0.8.4,<0.9.0",
        "required_tools": [
            "page_navigate",
            "page_resize",
            "wait_until",
            "frame_list",
            "frame_snapshot",
            "frame_find",
            "wait_for_element",
            "element_state_get",
            "element_scroll_into_view",
            "page_click_xy",
            "page_evaluate",
            "page_screenshot",
            "wait_time",
        ],
        "fixture": "cloudflare-test-sitekeys",
        "path": "skills/turnstile-testing/SKILL.md",
        "source_revision": SKILLS_SOURCE_REVISION,
        "source_url": f"{SKILLS_REPOSITORY_URL}/tree/{SKILLS_SOURCE_REVISION}/skills/turnstile-testing",
        "sha256": "6f6f3755db326854f00cc1618dddc3d9dd4d6840892921ea70054f22813a3113",
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

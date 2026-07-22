"""Concise initialization guidance for the standalone MCP core."""

from __future__ import annotations


def server_instructions(version: str) -> str:
    """Describe the stable core boundary without prescribing workflows."""

    return (
        f"DrissionPage MCP {version} is a standalone browser automation server. "
        "Use tools/list to discover its typed atomic capabilities and compose them "
        "for the current task. Optional, separately published Skills can be discovered "
        "through drissionpage://skills/catalog and use the repository convention "
        "skills/<skill-name>/SKILL.md; Skills are not required to use the MCP."
    )


__all__ = ["server_instructions"]

"""Browser-generated PDF and MHTML artifact operations."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ..response_errors import ErrorCode

if TYPE_CHECKING:
    from ..tab import PageTab

PageExportFormat = Literal["pdf", "mhtml"]


class ArtifactFileValidationError(ValueError):
    """Raised when an artifact path is not a stable file under its approved root."""


class ArtifactFileChangedError(RuntimeError):
    """Raised when an artifact changes while its contents are being inspected."""


@dataclass(frozen=True, slots=True)
class ArtifactFile:
    """Descriptor-backed integrity metadata for one browser artifact."""

    path: Path
    size_bytes: int
    sha256: str
    prefix: bytes


class PageExportError(RuntimeError):
    """Safe page-export failure without local path or page-content details."""

    code = ErrorCode.UNKNOWN_ERROR

    def __init__(self, reason_code: str):
        super().__init__(f"Page export failed ({reason_code}).")
        self.reason_code = reason_code


class PageArtifactOperations:
    """Own DrissionPage save calls and generated-file cleanup."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab

    async def save(
        self,
        directory: Path,
        filename: str,
        export_format: PageExportFormat,
        pdf_options: dict[str, Any],
    ) -> Path:
        save = getattr(self._tab.page, "save", None)
        if not callable(save):
            raise PageExportError("DRISSIONPAGE_SAVE_UNAVAILABLE")
        try:
            await asyncio.to_thread(
                save,
                path=directory,
                name=filename,
                as_pdf=export_format == "pdf",
                **(pdf_options if export_format == "pdf" else {}),
            )
        except Exception as exc:
            if not (
                export_format == "pdf"
                and isinstance(exc, ValueError)
                and "binary mode" in str(exc).lower()
            ):
                raise PageExportError("DRISSIONPAGE_SAVE_FAILED") from exc
            try:
                contents = await asyncio.to_thread(
                    save,
                    as_pdf=True,
                    **pdf_options,
                )
                if not isinstance(contents, bytes):
                    raise TypeError("DrissionPage PDF export did not return bytes")
                await asyncio.to_thread((directory / filename).write_bytes, contents)
            except Exception as fallback_exc:
                raise PageExportError("DRISSIONPAGE_PDF_FALLBACK_FAILED") from fallback_exc
        output = directory / filename
        return output

    async def cleanup(self, directory: Path | None) -> None:
        if directory is not None:
            await asyncio.to_thread(shutil.rmtree, directory, True)


def inspect_artifact_file(
    path: Path,
    *,
    approved_root: Path,
    prefix_bytes: int = 0,
) -> ArtifactFile:
    """Hash one stable regular file without following a replaced leaf path."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ArtifactFileValidationError(
            "Artifact is not a stable regular non-symlink file."
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ArtifactFileValidationError(
                "Artifact is not a regular non-symlink file."
            )
        resolved = _resolve_stable_artifact_path(
            path, approved_root, before.st_dev, before.st_ino
        )

        digest = hashlib.sha256()
        prefix = bytearray()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                if len(prefix) < prefix_bytes:
                    prefix.extend(chunk[: prefix_bytes - len(prefix)])
        after = os.fstat(descriptor)
        resolved_after = _resolve_stable_artifact_path(
            path,
            approved_root,
            before.st_dev,
            before.st_ino,
            expected=resolved,
        )
        if (
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_dev,
            before.st_ino,
        ) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_dev,
            after.st_ino,
        ):
            raise ArtifactFileChangedError(
                "Artifact changed while its integrity was being checked."
            )
        return ArtifactFile(
            path=resolved_after,
            size_bytes=after.st_size,
            sha256=digest.hexdigest(),
            prefix=bytes(prefix),
        )
    finally:
        os.close(descriptor)


def _resolve_stable_artifact_path(
    path: Path,
    approved_root: Path,
    device: int,
    inode: int,
    *,
    expected: Path | None = None,
) -> Path:
    message = (
        "Artifact escaped its approved root."
        if expected is None
        else "Artifact path changed during validation."
    )
    try:
        leaf = os.stat(path, follow_symlinks=False)
        resolved = path.resolve(strict=True)
        resolved.relative_to(approved_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ArtifactFileValidationError(message) from exc
    if (
        stat.S_ISLNK(leaf.st_mode)
        or (leaf.st_dev, leaf.st_ino) != (device, inode)
        or (expected is not None and resolved != expected)
    ):
        raise ArtifactFileValidationError("Artifact path changed during validation.")
    return resolved


__all__ = [
    "ArtifactFile",
    "ArtifactFileChangedError",
    "ArtifactFileValidationError",
    "PageArtifactOperations",
    "PageExportError",
    "PageExportFormat",
    "inspect_artifact_file",
]

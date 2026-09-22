# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Fail-closed local document ingestion and archive safety checks."""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from docling.docutrace.models import DocumentAsset, fingerprint


class IngestionError(ValueError):
    """A non-retryable document ingestion policy rejection."""


class UnsupportedFileError(IngestionError):
    pass


class MimeMismatchError(IngestionError):
    pass


class PageLimitError(IngestionError):
    pass


class EncryptedDocumentError(IngestionError):
    pass


@dataclass(frozen=True)
class IngestionPolicy:
    max_file_size: int = 20 * 1024 * 1024
    max_page_count: int = 100
    processing_timeout_seconds: float = 120.0
    max_archive_members: int = 2_000
    max_archive_uncompressed_size: int = 100 * 1024 * 1024
    max_compression_ratio: float = 100.0
    allowed_extensions: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                ".pdf",
                ".png",
                ".jpg",
                ".jpeg",
                ".docx",
                ".xlsx",
                ".pptx",
                ".txt",
                ".md",
                ".csv",
            }
        )
    )

    def __post_init__(self) -> None:
        if self.max_file_size < 1 or self.max_page_count < 1:
            raise ValueError("File and page limits must be positive")
        if self.processing_timeout_seconds <= 0:
            raise ValueError("Processing timeout must be positive")


_EXTENSION_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
}

_OFFICE_MARKERS = {
    ".docx": "word/",
    ".xlsx": "xl/",
    ".pptx": "ppt/",
}

_FORBIDDEN_ARCHIVE_NAMES = (
    "vbaproject.bin",
    "activex/",
    "embeddings/",
    "macros/",
)


def load_local_file(path: Path, *, allowed_root: Path | None = None) -> bytes:
    """Read one explicit local path, optionally constrained to a trusted root."""

    resolved = path.resolve(strict=True)
    if allowed_root is not None:
        root = allowed_root.resolve(strict=True)
        if resolved != root and root not in resolved.parents:
            raise IngestionError("Input path is outside the configured ingestion root")
    if not resolved.is_file():
        raise IngestionError("Input path is not a regular file")
    return resolved.read_bytes()


def _detect_media_type(data: bytes, suffix: str) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"PK\x03\x04"):
        return _EXTENSION_MEDIA_TYPES.get(suffix, "application/zip")
    if b"\x00" not in data[:4096]:
        if suffix in {".txt", ".md", ".csv"}:
            return _EXTENSION_MEDIA_TYPES[suffix]
        return "text/plain"
    return "application/octet-stream"


def _pdf_page_count(data: bytes) -> int:
    return max(1, len(re.findall(rb"/Type\s*/Page(?!s)\b", data)))


def _check_office_archive(data: bytes, suffix: str, policy: IngestionPolicy) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > policy.max_archive_members:
                raise IngestionError("Archive member limit exceeded")
            total_uncompressed = sum(member.file_size for member in members)
            if total_uncompressed > policy.max_archive_uncompressed_size:
                raise IngestionError("Archive uncompressed-size limit exceeded")
            names = [member.filename.replace("\\", "/").lower() for member in members]
            if "[content_types].xml" not in names:
                raise MimeMismatchError("Office archive is missing [Content_Types].xml")
            marker = _OFFICE_MARKERS[suffix]
            if not any(name.startswith(marker) for name in names):
                raise MimeMismatchError("Office container does not match its extension")
            for name, member in zip(names, members):
                path_parts = Path(name).parts
                if name.startswith("/") or ".." in path_parts:
                    raise IngestionError("Archive contains an unsafe member path")
                if any(marker in name for marker in _FORBIDDEN_ARCHIVE_NAMES):
                    raise IngestionError(
                        "Embedded macros or active content are not allowed"
                    )
                compressed = max(member.compress_size, 1)
                if member.file_size / compressed > policy.max_compression_ratio:
                    raise IngestionError("Archive compression-ratio limit exceeded")
    except zipfile.BadZipFile as error:
        raise IngestionError("Malformed Office container") from error


def validate_document(
    filename: str,
    data: bytes,
    *,
    declared_media_type: str | None = None,
    policy: IngestionPolicy | None = None,
) -> DocumentAsset:
    """Validate bytes without executing content or following embedded references."""

    active_policy = policy or IngestionPolicy()
    suffix = Path(filename).suffix.lower()
    if suffix in {".docm", ".xlsm", ".pptm"}:
        raise UnsupportedFileError("Macro-enabled Office files are not supported")
    if suffix not in active_policy.allowed_extensions:
        raise UnsupportedFileError(f"Unsupported file extension: {suffix or '<none>'}")
    if not data:
        raise IngestionError("Empty documents are not accepted")
    if len(data) > active_policy.max_file_size:
        raise IngestionError("Maximum file size exceeded")

    detected_media_type = _detect_media_type(data, suffix)
    expected_media_type = _EXTENSION_MEDIA_TYPES[suffix]
    if detected_media_type != expected_media_type:
        raise MimeMismatchError(
            f"Detected {detected_media_type}, expected {expected_media_type}"
        )
    if declared_media_type and declared_media_type != detected_media_type:
        raise MimeMismatchError(
            f"Declared {declared_media_type}, detected {detected_media_type}"
        )

    page_count = 1
    if suffix == ".pdf":
        if re.search(rb"/Encrypt\b", data):
            raise EncryptedDocumentError(
                "Password-protected PDFs require an explicitly reviewed credential flow"
            )
        page_count = _pdf_page_count(data)
    elif suffix in _OFFICE_MARKERS:
        _check_office_archive(data, suffix, active_policy)

    if page_count > active_policy.max_page_count:
        raise PageLimitError(
            f"Document has {page_count} pages; limit is {active_policy.max_page_count}"
        )

    digest = fingerprint(data)
    return DocumentAsset(
        asset_id=f"asset_{uuid.uuid5(uuid.NAMESPACE_URL, digest).hex}",
        filename=Path(filename).name,
        media_type=detected_media_type,
        data=data,
        fingerprint=digest,
        page_count=page_count,
    )

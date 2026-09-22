# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Citation-aware chunks and a vector-store-neutral adapter boundary."""

from __future__ import annotations

import uuid
from typing import Protocol

from docling.docutrace.models import (
    CitationAnchor,
    DocumentChunk,
    NormalizedDocument,
    Sensitivity,
)
from docling.docutrace.privacy import PrivacyPolicy, detect_sensitive_text


class ChunkSink(Protocol):
    def write(self, chunks: tuple[DocumentChunk, ...]) -> None: ...


def build_chunks(
    document: NormalizedDocument,
    *,
    max_characters: int = 1_200,
    privacy_policy: PrivacyPolicy | None = None,
) -> tuple[DocumentChunk, ...]:
    if max_characters < 64:
        raise ValueError("Chunk size must be at least 64 characters")
    active_policy = privacy_policy or PrivacyPolicy()
    chunks: list[DocumentChunk] = []
    for element in document.elements:
        text = element.text.strip()
        if not text:
            continue
        sensitivity = (
            Sensitivity.PII if detect_sensitive_text(text) else Sensitivity.INTERNAL
        )
        if sensitivity == Sensitivity.PII and active_policy.exclude_sensitive_chunks:
            continue
        for offset in range(0, len(text), max_characters):
            fragment = text[offset : offset + max_characters]
            seed = f"{document.document_id}:{element.element_id}:{offset}:{fragment}"
            anchor = CitationAnchor(
                citation_id=f"cite_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex}",
                document_id=document.document_id,
                page=element.page,
                element_id=element.element_id,
                text_span=fragment,
                bounding_box=element.bounding_box,
            )
            chunks.append(
                DocumentChunk(
                    chunk_id=f"chunk_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex}",
                    document_id=document.document_id,
                    text=fragment,
                    page_range=(element.page, element.page),
                    section_path=element.section_path,
                    source_element_ids=(element.element_id,),
                    content_type=element.label,
                    character_size=len(fragment),
                    sensitivity=sensitivity,
                    citation_anchors=(anchor,),
                )
            )
    return tuple(chunks)

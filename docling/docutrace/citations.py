# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Citation creation and integrity validation."""

from __future__ import annotations

import uuid

from docling.docutrace.models import (
    CitationAnchor,
    ExtractedField,
    NormalizedDocument,
)


class CitationIntegrityError(ValueError):
    pass


def build_citations(
    document: NormalizedDocument, fields: dict[str, ExtractedField]
) -> tuple[CitationAnchor, ...]:
    anchors: dict[tuple[int, str, str], CitationAnchor] = {}
    for field in fields.values():
        for evidence in field.evidence:
            key = (evidence.page, evidence.element_id, evidence.text_span)
            if key in anchors:
                continue
            citation_seed = f"{document.document_id}:{evidence.page}:{evidence.element_id}:{evidence.text_span}"
            anchors[key] = CitationAnchor(
                citation_id=f"cite_{uuid.uuid5(uuid.NAMESPACE_URL, citation_seed).hex}",
                document_id=document.document_id,
                page=evidence.page,
                element_id=evidence.element_id,
                text_span=evidence.text_span,
                bounding_box=evidence.bounding_box,
            )
    result = tuple(anchors.values())
    validate_citations(document, result)
    return result


def validate_citations(
    document: NormalizedDocument, citations: tuple[CitationAnchor, ...]
) -> None:
    elements = document.element_map()
    for citation in citations:
        if citation.document_id != document.document_id:
            raise CitationIntegrityError("Citation references a different document")
        if citation.page < 1 or citation.page > document.page_count:
            raise CitationIntegrityError("Citation page is outside the document")
        element = elements.get(citation.element_id)
        if element is None:
            raise CitationIntegrityError("Citation references a nonexistent element")
        if element.page != citation.page:
            raise CitationIntegrityError("Citation page does not match its element")
        if citation.text_span not in element.text:
            raise CitationIntegrityError("Citation text is not grounded in its element")
        if citation.bounding_box != element.bounding_box:
            raise CitationIntegrityError(
                "Citation bounding box does not match its element"
            )

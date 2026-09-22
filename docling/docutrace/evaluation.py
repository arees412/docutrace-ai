# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Deterministic golden-set evaluation without benchmark claims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docling.docutrace.citations import CitationIntegrityError, validate_citations
from docling.docutrace.models import DocumentType, ProcessingResult


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    expected_document_type: DocumentType
    expected_fields: dict[str, Any]


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    classification_match: bool
    matched_fields: int
    expected_fields: int
    citation_integrity: bool

    @property
    def passed(self) -> bool:
        return (
            self.classification_match
            and self.matched_fields == self.expected_fields
            and self.citation_integrity
        )


def evaluate(result: ProcessingResult, case: EvaluationCase) -> EvaluationResult:
    citation_integrity = True
    try:
        validate_citations(result.document, result.citations)
    except CitationIntegrityError:
        citation_integrity = False
    matches = sum(
        name in result.fields and result.fields[name].effective_value == expected
        for name, expected in case.expected_fields.items()
    )
    return EvaluationResult(
        case_id=case.case_id,
        classification_match=result.classification.document_type
        == case.expected_document_type,
        matched_fields=matches,
        expected_fields=len(case.expected_fields),
        citation_integrity=citation_integrity,
    )

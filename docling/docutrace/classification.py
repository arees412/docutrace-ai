# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Evidence-bearing deterministic document classification."""

from __future__ import annotations

from collections import Counter

from docling.docutrace.models import (
    ClassificationResult,
    ConfidenceState,
    DocumentType,
    EvidenceReference,
    NormalizedDocument,
)

_RULES: dict[DocumentType, tuple[str, ...]] = {
    DocumentType.INVOICE: ("invoice", "invoice number", "subtotal", "amount due"),
    DocumentType.RECEIPT: ("receipt", "cashier", "change", "thank you"),
    DocumentType.CONTRACT: (
        "agreement",
        "effective date",
        "governing law",
        "termination",
    ),
    DocumentType.FINANCIAL_STATEMENT: (
        "balance sheet",
        "income statement",
        "cash flows",
        "assets",
    ),
    DocumentType.PURCHASE_ORDER: ("purchase order", "po number", "ship to"),
    DocumentType.FORM: ("form", "signature", "date of birth"),
    DocumentType.REPORT: ("executive summary", "findings", "recommendations"),
    DocumentType.RESEARCH_PAPER: (
        "abstract",
        "methodology",
        "references",
        "doi",
    ),
}


def classify_document(document: NormalizedDocument) -> ClassificationResult:
    evidence_by_type: dict[DocumentType, list[EvidenceReference]] = {}
    counts: Counter[DocumentType] = Counter()
    for element in document.elements:
        text = element.text.casefold()
        for document_type, keywords in _RULES.items():
            matched = [keyword for keyword in keywords if keyword in text]
            if not matched:
                continue
            counts[document_type] += len(matched)
            evidence_by_type.setdefault(document_type, []).append(
                EvidenceReference(
                    document_id=document.document_id,
                    page=element.page,
                    element_id=element.element_id,
                    text_span=element.text[:240],
                    bounding_box=element.bounding_box,
                    extraction_method="deterministic_keyword_classifier",
                )
            )

    if not counts:
        return ClassificationResult(
            document_type=DocumentType.GENERIC,
            confidence=ConfidenceState.UNVERIFIED,
            evidence=(),
            classifier_source="deterministic_keyword_classifier",
        )

    best_type, best_score = counts.most_common(1)[0]
    competing_score = counts.most_common(2)[1][1] if len(counts) > 1 else 0
    if best_score >= 3 and best_score >= competing_score + 2:
        confidence = ConfidenceState.HIGH
    elif best_score >= 2 and best_score > competing_score:
        confidence = ConfidenceState.MEDIUM
    else:
        return ClassificationResult(
            document_type=DocumentType.GENERIC,
            confidence=ConfidenceState.LOW,
            evidence=tuple(evidence_by_type[best_type]),
            classifier_source="deterministic_keyword_classifier",
        )

    return ClassificationResult(
        document_type=best_type,
        confidence=confidence,
        evidence=tuple(evidence_by_type[best_type]),
        classifier_source="deterministic_keyword_classifier",
    )

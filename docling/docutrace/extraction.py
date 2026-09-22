# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Typed schemas and a deterministic evidence-backed extraction provider."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from docling.docutrace.models import (
    ConfidenceState,
    DocumentType,
    EvidenceReference,
    ExtractedField,
    ExtractionSchema,
    FieldDefinition,
    NormalizedDocument,
    ValidationStatus,
)


class ExtractionProvider(Protocol):
    name: str

    def extract(
        self, schema: ExtractionSchema, document: NormalizedDocument
    ) -> dict[str, ExtractedField]: ...


@dataclass(frozen=True)
class ExternalProviderPolicy:
    enabled: bool = False
    send_full_document: bool = False
    max_context_characters: int = 12_000


class ExternalExtractionProvider:
    """Explicit boundary for optional external providers.

    Concrete adapters must implement ``extract`` and enforce an enabled policy.
    DocuTrace ships no paid-provider binding and never enables this boundary in CI.
    """

    name = "external_provider"

    def __init__(self, policy: ExternalProviderPolicy | None = None) -> None:
        self.policy = policy or ExternalProviderPolicy()

    def extract(
        self, schema: ExtractionSchema, document: NormalizedDocument
    ) -> dict[str, ExtractedField]:
        del schema, document
        if not self.policy.enabled:
            raise PermissionError("External extraction requires explicit opt-in")
        raise NotImplementedError("No external provider adapter is configured")


def sample_invoice_schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="sample.invoice.v1",
        name="Sample invoice schema",
        document_types=(DocumentType.INVOICE,),
        version="1.0.0",
        sample=True,
        fields=(
            FieldDefinition(
                "invoice_number",
                "string",
                required=True,
                aliases=("invoice number", "invoice #", "invoice no"),
                validation={"pattern": r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,63}$"},
            ),
            FieldDefinition(
                "issue_date",
                "date",
                required=True,
                aliases=("issue date", "invoice date"),
            ),
            FieldDefinition("due_date", "date", aliases=("due date",)),
            FieldDefinition(
                "vendor_name",
                "string",
                required=True,
                aliases=("vendor", "supplier", "from"),
            ),
            FieldDefinition("subtotal", "decimal", aliases=("subtotal",)),
            FieldDefinition("tax", "decimal", aliases=("tax", "vat")),
            FieldDefinition(
                "total", "decimal", required=True, aliases=("total", "amount due")
            ),
            FieldDefinition(
                "currency",
                "currency",
                aliases=("currency",),
                validation={"allowed": ("USD", "EUR", "GBP", "PKR", "CAD", "AUD")},
            ),
            FieldDefinition("line_items", "array", aliases=("line items",)),
        ),
    )


def sample_contract_schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="sample.contract.v1",
        name="Sample contract schema",
        document_types=(DocumentType.CONTRACT,),
        version="1.0.0",
        sample=True,
        fields=(
            FieldDefinition(
                "parties", "string", required=True, aliases=("parties", "between")
            ),
            FieldDefinition(
                "effective_date", "date", required=True, aliases=("effective date",)
            ),
            FieldDefinition("termination_date", "date", aliases=("termination date",)),
            FieldDefinition("governing_law", "string", aliases=("governing law",)),
            FieldDefinition("payment_terms", "string", aliases=("payment terms",)),
            FieldDefinition("renewal_clause", "string", aliases=("renewal",)),
        ),
    )


_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}


def _normalize_date(value: str) -> str:
    cleaned = value.strip().rstrip(".")
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return date.fromisoformat(
                __import__("datetime")
                .datetime.strptime(cleaned, pattern)
                .date()
                .isoformat()
            ).isoformat()
        except ValueError:
            continue
    return cleaned


def _normalize_decimal(value: str) -> Decimal | str:
    cleaned = value.strip().replace(",", "")
    for symbol in _CURRENCY_SYMBOLS:
        cleaned = cleaned.replace(symbol, "")
    cleaned = re.sub(r"\s+[A-Za-z]{3}$", "", cleaned)
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return value.strip()


def _normalize_value(value: str, definition: FieldDefinition) -> Any:
    if definition.value_type == "date":
        return _normalize_date(value)
    if definition.value_type == "decimal":
        return _normalize_decimal(value)
    if definition.value_type == "currency":
        cleaned = value.strip().upper()
        return _CURRENCY_SYMBOLS.get(cleaned, cleaned)
    return value.strip()


def _value_after_alias(text: str, alias: str) -> str | None:
    pattern = re.compile(
        rf"(?i)(?:^|\b){re.escape(alias)}\s*(?:[:#=\-]|\bis\b)?\s*(.+?)\s*$"
    )
    match = pattern.search(text.strip())
    if match is None:
        return None
    value = match.group(1).strip()
    return value or None


class DeterministicExtractionProvider:
    """Alias-based local provider used for reproducible tests and offline flows."""

    name = "deterministic_alias_provider"

    def extract(
        self, schema: ExtractionSchema, document: NormalizedDocument
    ) -> dict[str, ExtractedField]:
        extracted: dict[str, ExtractedField] = {}
        for definition in schema.fields:
            if definition.value_type == "array" and document.tables:
                table = document.tables[0]
                rows = [dict(zip(table.headers, row)) for row in table.rows]
                evidence = list(table.row_evidence[0]) if table.row_evidence else []
                extracted[definition.name] = ExtractedField(
                    field_name=definition.name,
                    raw_value=rows,
                    normalized_value=rows,
                    confidence=(
                        ConfidenceState.HIGH if evidence else ConfidenceState.UNVERIFIED
                    ),
                    evidence=evidence,
                    sensitive=definition.sensitive,
                )
                continue

            candidate_value: str | None = None
            candidate_element = None
            matched_alias = ""
            for alias in definition.aliases or (definition.name.replace("_", " "),):
                for element in document.elements:
                    candidate_value = _value_after_alias(element.text, alias)
                    if candidate_value is not None:
                        candidate_element = element
                        matched_alias = alias
                        break
                if candidate_element is not None:
                    break

            if candidate_element is None or candidate_value is None:
                extracted[definition.name] = ExtractedField(
                    field_name=definition.name,
                    raw_value=None,
                    normalized_value=None,
                    confidence=ConfidenceState.UNVERIFIED,
                    evidence=[],
                    validation_status=(
                        ValidationStatus.MISSING
                        if definition.required
                        else ValidationStatus.VALID
                    ),
                    sensitive=definition.sensitive,
                )
                continue

            evidence = EvidenceReference(
                document_id=document.document_id,
                page=candidate_element.page,
                element_id=candidate_element.element_id,
                text_span=candidate_element.text,
                bounding_box=candidate_element.bounding_box,
                extraction_method=f"alias:{matched_alias}",
            )
            extracted[definition.name] = ExtractedField(
                field_name=definition.name,
                raw_value=candidate_value,
                normalized_value=_normalize_value(candidate_value, definition),
                confidence=ConfidenceState.MEDIUM,
                evidence=[evidence],
                sensitive=definition.sensitive,
            )
        return extracted

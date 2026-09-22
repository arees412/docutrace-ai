# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Human-review routing and immutable decision recording."""

from __future__ import annotations

from typing import Any

from docling.docutrace.models import (
    ConfidenceState,
    ExtractedField,
    ExtractionSchema,
    ReviewDecision,
    ReviewState,
    ValidationStatus,
    utc_now,
)


def fields_requiring_review(
    schema: ExtractionSchema, fields: dict[str, ExtractedField]
) -> tuple[str, ...]:
    definitions = {definition.name: definition for definition in schema.fields}
    required: list[str] = []
    for name, field in fields.items():
        definition = definitions[name]
        if (
            definition.review_required
            or field.sensitive
            or field.confidence in {ConfidenceState.LOW, ConfidenceState.UNVERIFIED}
            or field.validation_status
            in {
                ValidationStatus.INVALID,
                ValidationStatus.MISSING,
                ValidationStatus.REVIEW_REQUIRED,
            }
        ):
            field.validation_status = ValidationStatus.REVIEW_REQUIRED
            required.append(name)
    return tuple(required)


def apply_review_decision(
    field: ExtractedField,
    state: ReviewState,
    *,
    reviewed_value: Any = None,
    reason: str,
) -> ReviewDecision:
    if state == ReviewState.PENDING:
        raise ValueError("Pending is not a completed review decision")
    if state == ReviewState.CORRECTED and reviewed_value is None:
        raise ValueError("A corrected decision requires a reviewed value")
    decision = ReviewDecision(
        field_name=field.field_name,
        original_value=field.normalized_value,
        reviewed_value=reviewed_value,
        reviewer_state=state,
        reason=reason.strip(),
        timestamp=utc_now(),
    )
    field.review_state = state
    field.reviewed_value = reviewed_value
    return decision

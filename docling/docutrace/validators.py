# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Deterministic field and cross-field validation."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from docling.docutrace.models import (
    ConfidenceState,
    ExtractedField,
    ExtractionSchema,
    FieldDefinition,
    ValidationStatus,
)


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _validate_value(definition: FieldDefinition, value: Any) -> list[str]:
    messages: list[str] = []
    if value is None or value == "":
        if definition.required:
            messages.append("required field is missing")
        return messages

    if definition.value_type == "date":
        try:
            date.fromisoformat(str(value))
        except ValueError:
            messages.append("value is not an ISO date")
    elif definition.value_type == "decimal" and _decimal(value) is None:
        messages.append("value is not a decimal number")
    elif definition.value_type == "currency":
        if not re.fullmatch(r"[A-Z]{3}", str(value)):
            messages.append("currency must be a three-letter code")
    elif definition.value_type == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(value)):
            messages.append("value is not an email address")
    elif definition.value_type == "phone":
        if not re.fullmatch(r"\+?[0-9 ()-]{7,24}", str(value)):
            messages.append("value is not a supported phone format")
    elif definition.value_type == "percentage":
        number = _decimal(str(value).rstrip("%"))
        if number is None or number < 0 or number > 100:
            messages.append("percentage must be between 0 and 100")

    pattern = definition.validation.get("pattern")
    if pattern and re.fullmatch(str(pattern), str(value)) is None:
        messages.append("value does not match the configured pattern")
    allowed = definition.validation.get("allowed")
    if allowed and value not in allowed:
        messages.append("value is not in the configured allowlist")
    minimum = definition.validation.get("minimum")
    maximum = definition.validation.get("maximum")
    numeric = _decimal(value)
    if minimum is not None and (numeric is None or numeric < Decimal(str(minimum))):
        messages.append("value is below the configured minimum")
    if maximum is not None and (numeric is None or numeric > Decimal(str(maximum))):
        messages.append("value is above the configured maximum")
    return messages


def validate_fields(
    schema: ExtractionSchema,
    fields: dict[str, ExtractedField],
    *,
    monetary_tolerance: Decimal = Decimal("0.02"),
) -> None:
    definitions = {definition.name: definition for definition in schema.fields}
    for name, definition in definitions.items():
        field = fields[name]
        messages = _validate_value(definition, field.effective_value)
        field.validation_messages = messages
        if field.effective_value is None and definition.required:
            field.validation_status = ValidationStatus.MISSING
        elif messages:
            field.validation_status = ValidationStatus.INVALID
        else:
            field.validation_status = ValidationStatus.VALID

    _validate_date_order(fields, "issue_date", "due_date")
    _validate_date_order(fields, "effective_date", "termination_date")

    subtotal = _decimal(
        fields.get(
            "subtotal", ExtractedField("", None, None, ConfidenceState.UNVERIFIED, [])
        ).effective_value
    )
    tax = _decimal(
        fields.get(
            "tax", ExtractedField("", None, None, ConfidenceState.UNVERIFIED, [])
        ).effective_value
    )
    total_field = fields.get("total")
    total = _decimal(total_field.effective_value) if total_field else None
    if subtotal is not None and tax is not None and total is not None:
        if abs((subtotal + tax) - total) > monetary_tolerance:
            assert total_field is not None
            total_field.validation_status = ValidationStatus.INVALID
            total_field.validation_messages.append(
                f"subtotal plus tax differs from total by more than {monetary_tolerance}"
            )

    for field in fields.values():
        if not field.evidence:
            field.confidence = ConfidenceState.UNVERIFIED
        elif field.validation_status in {
            ValidationStatus.INVALID,
            ValidationStatus.MISSING,
        }:
            field.confidence = ConfidenceState.LOW
        elif field.confidence == ConfidenceState.MEDIUM:
            field.confidence = ConfidenceState.HIGH


def _validate_date_order(
    fields: dict[str, ExtractedField], start_name: str, end_name: str
) -> None:
    start_field = fields.get(start_name)
    end_field = fields.get(end_name)
    if start_field is None or end_field is None:
        return
    try:
        start = date.fromisoformat(str(start_field.effective_value))
        end = date.fromisoformat(str(end_field.effective_value))
    except ValueError:
        return
    if start > end:
        end_field.validation_status = ValidationStatus.INVALID
        end_field.validation_messages.append(f"{end_name} precedes {start_name}")

# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Deterministic JSON and Markdown result projections."""

from __future__ import annotations

import json
from typing import Any

from docling.docutrace.models import ProcessingResult, to_primitive
from docling.docutrace.privacy import PrivacyPolicy, redact_text


def _redact_projection(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact_projection(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_projection(item) for key, item in value.items()}
    return value


def result_to_dict(
    result: ProcessingResult, *, privacy_policy: PrivacyPolicy | None = None
) -> dict[str, Any]:
    active_policy = privacy_policy or PrivacyPolicy()
    fields: dict[str, Any] = {}
    for name, field in sorted(result.fields.items()):
        value = field.effective_value
        if active_policy.redact_exports and value is not None and field.sensitive:
            value = redact_text(str(value))
        fields[name] = {
            "value": to_primitive(value),
            "confidence": field.confidence.value,
            "validation_status": field.validation_status.value,
            "review_state": field.review_state.value if field.review_state else None,
            "evidence": to_primitive(field.evidence),
        }
    projection = {
        "job": to_primitive(result.job),
        "classification": to_primitive(result.classification),
        "schema": {
            "schema_id": result.schema.schema_id,
            "version": result.schema.version,
        },
        "fields": fields,
        "tables": to_primitive(result.tables),
        "citations": to_primitive(result.citations),
        "chunks": to_primitive(result.chunks),
        "metrics": to_primitive(result.metrics),
        "provenance": to_primitive(result.provenance),
    }
    if active_policy.redact_exports:
        projection = _redact_projection(projection)
    return projection


def result_to_json(result: ProcessingResult) -> str:
    return json.dumps(
        result_to_dict(result), sort_keys=True, indent=2, ensure_ascii=True
    )


def result_to_markdown(result: ProcessingResult) -> str:
    lines = [
        f"# DocuTrace result: {result.asset.filename}",
        "",
        f"- Status: `{result.job.status.value}`",
        f"- Classification: `{result.classification.document_type.value}`",
        f"- Schema: `{result.schema.schema_id}`",
        "",
        "## Fields",
        "",
    ]
    for name, value in sorted(result_to_dict(result)["fields"].items()):
        lines.append(f"- `{name}`: {value['value']!s} ({value['confidence']})")
    return "\n".join(lines) + "\n"

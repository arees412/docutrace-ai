# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Configurable detection and fail-closed handling of sensitive text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from docling.docutrace.models import ExtractedField, Sensitivity


@dataclass(frozen=True)
class PrivacyFinding:
    category: str
    start: int
    end: int
    masked_value: str


@dataclass(frozen=True)
class PrivacyPolicy:
    redact_exports: bool = True
    exclude_sensitive_chunks: bool = True
    allow_external_sensitive_context: bool = False


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
    ("phone", re.compile(r"(?<!\w)\+?[0-9][0-9 ()-]{6,22}[0-9](?!\w)")),
    ("payment_card", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    (
        "credential",
        re.compile(r"(?i)\b(?:api[_ -]?key|access[_ -]?token|secret)\s*[:=]\s*\S+"),
    ),
)


def detect_sensitive_text(text: str) -> tuple[PrivacyFinding, ...]:
    findings: list[PrivacyFinding] = []
    for category, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                PrivacyFinding(
                    category, match.start(), match.end(), f"[REDACTED:{category}]"
                )
            )
    return tuple(sorted(findings, key=lambda finding: (finding.start, finding.end)))


def redact_text(text: str) -> str:
    redacted = text
    for finding in reversed(detect_sensitive_text(text)):
        redacted = (
            redacted[: finding.start] + finding.masked_value + redacted[finding.end :]
        )
    return redacted


def field_sensitivity(field: ExtractedField) -> Sensitivity:
    if field.sensitive:
        return Sensitivity.PII
    value = field.effective_value
    if value is not None and detect_sensitive_text(str(value)):
        return Sensitivity.PII
    return Sensitivity.INTERNAL

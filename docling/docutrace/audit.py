# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Tamper-evident, metadata-only audit events."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from docling.docutrace.models import AuditEvent, canonical_json, fingerprint, utc_now

_FORBIDDEN_KEYS = {
    "data",
    "bytes",
    "content",
    "document",
    "password",
    "secret",
    "token",
}


def _sanitize(metadata: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized = key.casefold()
        if any(forbidden in normalized for forbidden in _FORBIDDEN_KEYS):
            sanitized[key] = "[OMITTED]"
        elif isinstance(value, str) and len(value) > 256:
            sanitized[key] = value[:253] + "..."
        else:
            sanitized[key] = value
    return sanitized


def append_audit_event(
    events: list[AuditEvent], event_type: str, metadata: Mapping[str, Any]
) -> AuditEvent:
    safe_metadata = _sanitize(metadata)
    previous_hash = events[-1].event_hash if events else None
    payload = {
        "sequence": len(events) + 1,
        "event_type": event_type,
        "metadata": safe_metadata,
        "previous_hash": previous_hash,
    }
    event = AuditEvent(
        sequence=len(events) + 1,
        event_type=event_type,
        timestamp=utc_now(),
        metadata=safe_metadata,
        previous_hash=previous_hash,
        event_hash=fingerprint(canonical_json(payload)),
    )
    events.append(event)
    return event


def verify_audit_chain(events: list[AuditEvent]) -> bool:
    for index, event in enumerate(events):
        previous_hash = events[index - 1].event_hash if index else None
        payload = {
            "sequence": event.sequence,
            "event_type": event.event_type,
            "metadata": event.metadata,
            "previous_hash": previous_hash,
        }
        if event.previous_hash != previous_hash:
            return False
        if event.event_hash != fingerprint(canonical_json(payload)):
            return False
    return True

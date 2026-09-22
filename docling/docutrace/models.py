# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Typed domain models for the DocuTrace governed processing layer."""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    PARSING = "parsing"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    VALIDATING_OUTPUT = "validating_output"
    REVIEW_REQUIRED = "review_required"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, enum.Enum):
    INVOICE = "invoice"
    RECEIPT = "receipt"
    CONTRACT = "contract"
    FINANCIAL_STATEMENT = "financial_statement"
    PURCHASE_ORDER = "purchase_order"
    FORM = "form"
    REPORT = "report"
    RESEARCH_PAPER = "research_paper"
    GENERIC = "generic_document"


class ConfidenceState(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


class ReviewState(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ValidationStatus(str, enum.Enum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"
    REVIEW_REQUIRED = "review_required"


class Sensitivity(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "pii"
    RESTRICTED = "restricted"


class RetryDisposition(str, enum.Enum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"


@dataclasses.dataclass(frozen=True)
class BoundingBox:
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        if self.left > self.right or self.top > self.bottom:
            raise ValueError("Bounding box coordinates are inverted")


@dataclasses.dataclass(frozen=True)
class EvidenceReference:
    document_id: str
    page: int
    element_id: str
    text_span: str
    bounding_box: BoundingBox | None
    extraction_method: str


@dataclasses.dataclass(frozen=True)
class CitationAnchor:
    citation_id: str
    document_id: str
    page: int
    element_id: str
    text_span: str
    bounding_box: BoundingBox | None


@dataclasses.dataclass(frozen=True)
class NormalizedElement:
    element_id: str
    page: int
    text: str
    label: str = "text"
    bounding_box: BoundingBox | None = None
    section_path: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class TableCell:
    row_start: int
    row_end: int
    column_start: int
    column_end: int
    text: str
    page: int
    element_id: str
    bounding_box: BoundingBox | None = None


@dataclasses.dataclass(frozen=True)
class NormalizedTable:
    table_id: str
    page: int
    headers: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    source_cells: tuple[TableCell, ...]
    row_evidence: tuple[tuple[EvidenceReference, ...], ...]
    merged_cells: bool = False


@dataclasses.dataclass(frozen=True)
class NormalizedDocument:
    document_id: str
    filename: str
    media_type: str
    page_count: int
    elements: tuple[NormalizedElement, ...]
    tables: tuple[NormalizedTable, ...] = ()
    parser_backend: str = "unknown"
    ocr_engine: str | None = None
    ocr_pages: tuple[int, ...] = ()
    figures_detected: int = 0

    @property
    def text(self) -> str:
        return "\n".join(element.text for element in self.elements if element.text)

    def element_map(self) -> dict[str, NormalizedElement]:
        return {element.element_id: element for element in self.elements}


@dataclasses.dataclass(frozen=True)
class FieldDefinition:
    name: str
    value_type: str
    required: bool = False
    aliases: tuple[str, ...] = ()
    validation: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    confidence_threshold: ConfidenceState = ConfidenceState.MEDIUM
    sensitive: bool = False
    review_required: bool = False


@dataclasses.dataclass(frozen=True)
class ExtractionSchema:
    schema_id: str
    name: str
    document_types: tuple[DocumentType, ...]
    version: str
    fields: tuple[FieldDefinition, ...]
    sample: bool = True


@dataclasses.dataclass
class ExtractedField:
    field_name: str
    raw_value: Any
    normalized_value: Any
    confidence: ConfidenceState
    evidence: list[EvidenceReference]
    validation_status: ValidationStatus = ValidationStatus.VALID
    validation_messages: list[str] = dataclasses.field(default_factory=list)
    review_state: ReviewState | None = None
    reviewed_value: Any = None
    sensitive: bool = False

    @property
    def effective_value(self) -> Any:
        if self.review_state == ReviewState.CORRECTED:
            return self.reviewed_value
        if self.review_state == ReviewState.REJECTED:
            return None
        return self.normalized_value


@dataclasses.dataclass(frozen=True)
class ReviewDecision:
    field_name: str
    original_value: Any
    reviewed_value: Any
    reviewer_state: ReviewState
    reason: str
    timestamp: datetime


@dataclasses.dataclass(frozen=True)
class ClassificationResult:
    document_type: DocumentType
    confidence: ConfidenceState
    evidence: tuple[EvidenceReference, ...]
    classifier_source: str


@dataclasses.dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    text: str
    page_range: tuple[int, int]
    section_path: tuple[str, ...]
    source_element_ids: tuple[str, ...]
    content_type: str
    character_size: int
    sensitivity: Sensitivity
    citation_anchors: tuple[CitationAnchor, ...]


@dataclasses.dataclass(frozen=True)
class AuditEvent:
    sequence: int
    event_type: str
    timestamp: datetime
    metadata: Mapping[str, Any]
    previous_hash: str | None
    event_hash: str


@dataclasses.dataclass(frozen=True)
class ProcessingEvent:
    stage: str
    status: str
    timestamp: datetime
    detail: str = ""


@dataclasses.dataclass
class ProcessingMetrics:
    processing_duration_ms: int = 0
    pages_processed: int = 0
    ocr_pages: int = 0
    tables_detected: int = 0
    figures_detected: int = 0
    fields_extracted: int = 0
    fields_requiring_review: int = 0
    parser_backend: str = "unknown"
    ocr_engine: str | None = None
    failure_category: str | None = None
    attempts: int = 0


@dataclasses.dataclass(frozen=True)
class ProvenanceRecord:
    input_fingerprint: str
    source_filename: str
    parser_profile: str
    docling_version: str
    schema_version: str
    extraction_provider: str
    started_at: datetime
    completed_at: datetime | None
    output_fingerprint: str | None


@dataclasses.dataclass(frozen=True)
class DocumentAsset:
    asset_id: str
    filename: str
    media_type: str
    data: bytes
    fingerprint: str
    page_count: int


@dataclasses.dataclass(frozen=True)
class DocumentRevision:
    revision_id: str
    asset_id: str
    fingerprint: str
    created_at: datetime


@dataclasses.dataclass
class DocumentJob:
    job_id: str
    filename: str
    media_type: str
    status: JobStatus
    created_at: datetime
    parser_profile: str
    schema_id: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    idempotency_key: str | None = None


@dataclasses.dataclass
class ProcessingResult:
    job: DocumentJob
    asset: DocumentAsset
    revision: DocumentRevision
    document: NormalizedDocument
    classification: ClassificationResult
    schema: ExtractionSchema
    fields: dict[str, ExtractedField]
    tables: tuple[NormalizedTable, ...]
    citations: tuple[CitationAnchor, ...]
    chunks: tuple[DocumentChunk, ...]
    review_decisions: list[ReviewDecision]
    audit_events: list[AuditEvent]
    processing_events: list[ProcessingEvent]
    metrics: ProcessingMetrics
    provenance: ProvenanceRecord

    @property
    def requires_review(self) -> bool:
        return self.job.status == JobStatus.REVIEW_REQUIRED


def to_primitive(value: Any) -> Any:
    """Convert typed domain objects to deterministic JSON-compatible values."""

    if dataclasses.is_dataclass(value):
        return {
            field.name: to_primitive(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_primitive(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_primitive(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def fingerprint(value: Any) -> str:
    payload = (
        value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    )
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

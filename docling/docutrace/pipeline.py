# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Governed, idempotent document-intelligence orchestration."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from docling import __version__ as docling_version
from docling.docutrace.adapters import DeterministicFixtureParser, ParserAdapter
from docling.docutrace.audit import append_audit_event
from docling.docutrace.citations import build_citations
from docling.docutrace.classification import classify_document
from docling.docutrace.extraction import (
    DeterministicExtractionProvider,
    ExtractionProvider,
    sample_contract_schema,
    sample_invoice_schema,
)
from docling.docutrace.ingestion import IngestionPolicy, validate_document
from docling.docutrace.models import (
    AuditEvent,
    ClassificationResult,
    ConfidenceState,
    DocumentJob,
    DocumentRevision,
    DocumentType,
    ExtractionSchema,
    JobStatus,
    ProcessingEvent,
    ProcessingMetrics,
    ProcessingResult,
    ProvenanceRecord,
    RetryDisposition,
    fingerprint,
    to_primitive,
    utc_now,
)
from docling.docutrace.profiles import get_profile
from docling.docutrace.rag import build_chunks
from docling.docutrace.review import fields_requiring_review
from docling.docutrace.validators import validate_fields


class ProcessingFailure(RuntimeError):
    disposition = RetryDisposition.NON_RETRYABLE


class RetryableProcessingFailure(ProcessingFailure):
    disposition = RetryDisposition.RETRYABLE


def _generic_schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="sample.generic.v1",
        name="Generic document schema",
        document_types=(DocumentType.GENERIC,),
        version="1.0.0",
        fields=(),
        sample=True,
    )


@dataclass(frozen=True)
class PipelineConfig:
    parser_profile: str = "balanced"
    max_retries: int = 1
    ingestion_policy: IngestionPolicy = field(default_factory=IngestionPolicy)

    def __post_init__(self) -> None:
        if self.max_retries < 0 or self.max_retries > 3:
            raise ValueError("Retries must be bounded between zero and three")


class DocuTracePipeline:
    def __init__(
        self,
        *,
        parser: ParserAdapter | None = None,
        provider: ExtractionProvider | None = None,
        schemas: tuple[ExtractionSchema, ...] | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        self.parser = parser or DeterministicFixtureParser()
        self.provider = provider or DeterministicExtractionProvider()
        self.config = config or PipelineConfig()
        configured_schemas = schemas or (
            sample_invoice_schema(),
            sample_contract_schema(),
            _generic_schema(),
        )
        self.schemas = {schema.schema_id: schema for schema in configured_schemas}
        self._cache: dict[str, ProcessingResult] = {}

    def process(
        self,
        filename: str,
        data: bytes,
        *,
        schema_id: str | None = None,
        declared_media_type: str | None = None,
        idempotency_key: str | None = None,
    ) -> ProcessingResult:
        asset = validate_document(
            filename,
            data,
            declared_media_type=declared_media_type,
            policy=self.config.ingestion_policy,
        )
        cache_key = idempotency_key or fingerprint(
            {
                "asset": asset.fingerprint,
                "profile": self.config.parser_profile,
                "schema": schema_id,
                "parser": self.parser.name,
                "provider": self.provider.name,
            }
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

        started_at = utc_now()
        monotonic_started_at = time.monotonic()
        job = DocumentJob(
            job_id=f"job_{uuid.uuid5(uuid.NAMESPACE_URL, cache_key).hex}",
            filename=asset.filename,
            media_type=asset.media_type,
            status=JobStatus.VALIDATING,
            created_at=started_at,
            started_at=started_at,
            parser_profile=self.config.parser_profile,
            schema_id=schema_id or "auto",
            idempotency_key=cache_key,
        )
        audit_events: list[AuditEvent] = []
        processing_events: list[ProcessingEvent] = []
        append_audit_event(
            audit_events,
            "ingestion.accepted",
            {
                "asset_id": asset.asset_id,
                "fingerprint": asset.fingerprint,
                "size": len(data),
            },
        )
        processing_events.append(ProcessingEvent("ingestion", "completed", utc_now()))
        profile = get_profile(self.config.parser_profile)
        metrics = ProcessingMetrics(pages_processed=asset.page_count)

        document = None
        for attempt in range(1, self.config.max_retries + 2):
            metrics.attempts = attempt
            try:
                job.status = JobStatus.PARSING
                document = self.parser.parse(asset, profile)
                break
            except RetryableProcessingFailure:
                if attempt > self.config.max_retries:
                    job.status = JobStatus.FAILED
                    metrics.failure_category = "retry_exhausted"
                    raise
                processing_events.append(
                    ProcessingEvent(
                        "parsing", "retrying", utc_now(), f"attempt {attempt}"
                    )
                )
        if document is None:
            raise ProcessingFailure("Parser returned no document")
        if (
            time.monotonic() - monotonic_started_at
            > self.config.ingestion_policy.processing_timeout_seconds
        ):
            raise ProcessingFailure("Processing timeout exceeded")
        processing_events.append(ProcessingEvent("parsing", "completed", utc_now()))
        append_audit_event(
            audit_events,
            "parsing.completed",
            {"backend": document.parser_backend, "pages": document.page_count},
        )

        job.status = JobStatus.CLASSIFYING
        classification = classify_document(document)
        schema = self._select_schema(schema_id, classification)
        job.schema_id = schema.schema_id
        processing_events.append(
            ProcessingEvent("classification", "completed", utc_now())
        )

        job.status = JobStatus.EXTRACTING
        fields = self.provider.extract(schema, document)
        job.status = JobStatus.VALIDATING_OUTPUT
        validate_fields(schema, fields)
        citations = build_citations(document, fields)
        chunks = build_chunks(document)
        review_fields = fields_requiring_review(schema, fields)
        needs_classification_review = classification.confidence in {
            ConfidenceState.LOW,
            ConfidenceState.UNVERIFIED,
        }
        job.status = (
            JobStatus.REVIEW_REQUIRED
            if review_fields or needs_classification_review
            else JobStatus.COMPLETED
        )
        completed_at = utc_now()
        job.completed_at = completed_at
        metrics.ocr_pages = len(document.ocr_pages)
        metrics.tables_detected = len(document.tables)
        metrics.figures_detected = document.figures_detected
        metrics.fields_extracted = sum(
            field.effective_value is not None for field in fields.values()
        )
        metrics.fields_requiring_review = len(review_fields)
        metrics.parser_backend = document.parser_backend
        metrics.ocr_engine = document.ocr_engine
        metrics.processing_duration_ms = max(
            0, int((completed_at - started_at).total_seconds() * 1000)
        )
        append_audit_event(
            audit_events,
            "processing.completed",
            {
                "status": job.status.value,
                "schema_id": schema.schema_id,
                "review_field_count": len(review_fields),
            },
        )
        processing_events.append(
            ProcessingEvent("governance", job.status.value, completed_at)
        )
        output_projection: dict[str, Any] = {
            "classification": to_primitive(classification),
            "fields": to_primitive(fields),
            "tables": to_primitive(document.tables),
            "citations": to_primitive(citations),
            "chunks": to_primitive(chunks),
        }
        provenance = ProvenanceRecord(
            input_fingerprint=asset.fingerprint,
            source_filename=asset.filename,
            parser_profile=self.config.parser_profile,
            docling_version=docling_version,
            schema_version=schema.version,
            extraction_provider=self.provider.name,
            started_at=started_at,
            completed_at=completed_at,
            output_fingerprint=fingerprint(output_projection),
        )
        revision = DocumentRevision(
            revision_id=f"rev_{uuid.uuid5(uuid.NAMESPACE_URL, asset.fingerprint).hex}",
            asset_id=asset.asset_id,
            fingerprint=asset.fingerprint,
            created_at=started_at,
        )
        result = ProcessingResult(
            job=job,
            asset=asset,
            revision=revision,
            document=document,
            classification=classification,
            schema=schema,
            fields=fields,
            tables=document.tables,
            citations=citations,
            chunks=chunks,
            review_decisions=[],
            audit_events=audit_events,
            processing_events=processing_events,
            metrics=metrics,
            provenance=provenance,
        )
        self._cache[cache_key] = result
        return result

    def _select_schema(
        self, schema_id: str | None, classification: ClassificationResult
    ) -> ExtractionSchema:
        if schema_id is not None:
            try:
                return self.schemas[schema_id]
            except KeyError as error:
                raise ProcessingFailure(
                    f"Unknown extraction schema: {schema_id}"
                ) from error
        for schema in self.schemas.values():
            if classification.document_type in schema.document_types:
                return schema
        return _generic_schema()

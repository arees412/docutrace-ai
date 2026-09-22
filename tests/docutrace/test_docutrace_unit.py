# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from docling.docutrace.adapters import DoclingParserAdapter, fixture_pdf
from docling.docutrace.audit import append_audit_event, verify_audit_chain
from docling.docutrace.citations import (
    CitationIntegrityError,
    build_citations,
    validate_citations,
)
from docling.docutrace.classification import classify_document
from docling.docutrace.exports import result_to_json, result_to_markdown
from docling.docutrace.extraction import (
    DeterministicExtractionProvider,
    ExternalExtractionProvider,
    sample_contract_schema,
    sample_invoice_schema,
)
from docling.docutrace.ingestion import (
    EncryptedDocumentError,
    IngestionError,
    IngestionPolicy,
    MimeMismatchError,
    PageLimitError,
    UnsupportedFileError,
    load_local_file,
    validate_document,
)
from docling.docutrace.models import (
    BoundingBox,
    ConfidenceState,
    DocumentType,
    EvidenceReference,
    ExtractedField,
    ExtractionSchema,
    FieldDefinition,
    JobStatus,
    NormalizedDocument,
    NormalizedElement,
    ReviewState,
    TableCell,
    ValidationStatus,
    canonical_json,
)
from docling.docutrace.pipeline import (
    DocuTracePipeline,
    PipelineConfig,
    ProcessingFailure,
    RetryableProcessingFailure,
)
from docling.docutrace.privacy import detect_sensitive_text, redact_text
from docling.docutrace.profiles import get_profile
from docling.docutrace.rag import build_chunks
from docling.docutrace.review import apply_review_decision, fields_requiring_review
from docling.docutrace.tables import normalize_table, table_to_json
from docling.docutrace.validators import validate_fields


def _document(*lines: str) -> NormalizedDocument:
    return NormalizedDocument(
        document_id="doc_1",
        filename="fixture.pdf",
        media_type="application/pdf",
        page_count=1,
        elements=tuple(
            NormalizedElement(
                f"el_{index}",
                1,
                line,
                bounding_box=BoundingBox(0, index, 10, index + 1),
            )
            for index, line in enumerate(lines, start=1)
        ),
        parser_backend="test",
    )


def _office_bytes(prefix: str = "word/", *, unsafe_name: str | None = None) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(f"{prefix}document.xml", "<document />")
        if unsafe_name:
            archive.writestr(unsafe_name, "unsafe")
    return stream.getvalue()


def test_rejects_empty_document() -> None:
    with pytest.raises(IngestionError, match="Empty"):
        validate_document("empty.pdf", b"")


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFileError):
        validate_document("payload.exe", b"MZ")


def test_rejects_mime_mismatch() -> None:
    with pytest.raises(MimeMismatchError):
        validate_document("image.png", b"plain text")


def test_rejects_declared_mime_mismatch() -> None:
    with pytest.raises(MimeMismatchError):
        validate_document("note.txt", b"text", declared_media_type="application/pdf")


def test_rejects_size_limit() -> None:
    with pytest.raises(IngestionError, match="size"):
        validate_document("note.txt", b"12345", policy=IngestionPolicy(max_file_size=4))


def test_rejects_page_limit() -> None:
    payload = fixture_pdf(["hello"], pages=2)
    with pytest.raises(PageLimitError):
        validate_document("two.pdf", payload, policy=IngestionPolicy(max_page_count=1))


def test_rejects_encrypted_pdf() -> None:
    with pytest.raises(EncryptedDocumentError):
        validate_document("locked.pdf", b"%PDF-1.4\n/Encrypt true\n/Type /Page")


def test_rejects_macro_extension() -> None:
    with pytest.raises(UnsupportedFileError):
        validate_document("macro.docm", _office_bytes())


def test_rejects_office_traversal() -> None:
    with pytest.raises(IngestionError, match="unsafe"):
        validate_document("bad.docx", _office_bytes(unsafe_name="../escape.txt"))


def test_rejects_office_active_content() -> None:
    with pytest.raises(IngestionError, match="active content"):
        validate_document(
            "macro-hidden.docx", _office_bytes(unsafe_name="word/vbaProject.bin")
        )


def test_rejects_archive_compression_abuse() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "0" * 100_000)
    with pytest.raises(IngestionError, match="compression-ratio"):
        validate_document(
            "compressed.docx",
            stream.getvalue(),
            policy=IngestionPolicy(max_compression_ratio=10),
        )


def test_accepts_minimal_office_container() -> None:
    asset = validate_document("safe.docx", _office_bytes())
    assert asset.media_type.endswith("wordprocessingml.document")


def test_local_loader_stays_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    file = root / "input.txt"
    file.write_bytes(b"safe")
    assert load_local_file(file, allowed_root=root) == b"safe"


def test_local_loader_rejects_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    file = tmp_path / "outside.txt"
    file.write_bytes(b"no")
    with pytest.raises(IngestionError, match="outside"):
        load_local_file(file, allowed_root=root)


def test_bounding_box_rejects_inversion() -> None:
    with pytest.raises(ValueError, match="inverted"):
        BoundingBox(5, 0, 1, 2)


def test_canonical_json_is_order_stable() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_invoice_classification_is_evidence_backed() -> None:
    result = classify_document(
        _document("Invoice", "Invoice Number: I-1", "Subtotal", "Amount Due")
    )
    assert result.document_type == DocumentType.INVOICE
    assert result.confidence == ConfidenceState.HIGH
    assert result.evidence


def test_ambiguous_classification_falls_back() -> None:
    result = classify_document(_document("Invoice and agreement"))
    assert result.document_type == DocumentType.GENERIC
    assert result.confidence == ConfidenceState.LOW


def test_unknown_classification_is_unverified() -> None:
    result = classify_document(_document("unstructured material"))
    assert result.document_type == DocumentType.GENERIC
    assert result.confidence == ConfidenceState.UNVERIFIED


def test_extraction_normalizes_date_and_decimal() -> None:
    document = _document(
        "Invoice Number: I-2",
        "Invoice Date: 09/22/2026",
        "Vendor: Acme",
        "Total: $1,234.50",
    )
    fields = DeterministicExtractionProvider().extract(
        sample_invoice_schema(), document
    )
    assert fields["issue_date"].normalized_value == "2026-09-22"
    assert fields["total"].normalized_value == Decimal("1234.50")


def test_external_provider_is_disabled_by_default() -> None:
    with pytest.raises(PermissionError, match="opt-in"):
        ExternalExtractionProvider().extract(
            sample_invoice_schema(), _document("Invoice")
        )


def test_required_field_validator_marks_missing() -> None:
    schema = ExtractionSchema(
        "s",
        "s",
        (DocumentType.GENERIC,),
        "1",
        (FieldDefinition("x", "string", required=True),),
    )
    fields = {"x": ExtractedField("x", None, None, ConfidenceState.UNVERIFIED, [])}
    validate_fields(schema, fields)
    assert fields["x"].validation_status == ValidationStatus.MISSING


def test_validator_rejects_bad_currency() -> None:
    schema = ExtractionSchema(
        "s",
        "s",
        (DocumentType.GENERIC,),
        "1",
        (FieldDefinition("currency", "currency"),),
    )
    fields = {
        "currency": ExtractedField(
            "currency", "dollars", "dollars", ConfidenceState.MEDIUM, [_evidence()]
        )
    }
    validate_fields(schema, fields)
    assert fields["currency"].validation_status == ValidationStatus.INVALID


def test_validator_checks_date_order() -> None:
    fields = DeterministicExtractionProvider().extract(
        sample_contract_schema(),
        _document(
            "Parties: A and B",
            "Effective Date: 2026-10-01",
            "Termination Date: 2026-09-01",
        ),
    )
    validate_fields(sample_contract_schema(), fields)
    assert fields["termination_date"].validation_status == ValidationStatus.INVALID


def test_validator_checks_invoice_total() -> None:
    document = _document(
        "Invoice Number: I-3",
        "Invoice Date: 2026-09-22",
        "Vendor: Acme",
        "Subtotal: 10.00",
        "Tax: 2.00",
        "Total: 99.00",
    )
    fields = DeterministicExtractionProvider().extract(
        sample_invoice_schema(), document
    )
    validate_fields(sample_invoice_schema(), fields)
    assert fields["total"].validation_status == ValidationStatus.INVALID


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        "doc_1", 1, "el_1", "Invoice Number: I-1", BoundingBox(0, 1, 10, 2), "test"
    )


def test_builds_and_validates_citations() -> None:
    document = _document("Invoice Number: I-1")
    field = ExtractedField(
        "invoice_number", "I-1", "I-1", ConfidenceState.HIGH, [_evidence()]
    )
    citations = build_citations(document, {"invoice_number": field})
    validate_citations(document, citations)
    assert citations[0].element_id == "el_1"


def test_rejects_citation_text_not_in_element() -> None:
    document = _document("Invoice Number: I-1")
    field = ExtractedField(
        "invoice_number",
        "I-1",
        "I-1",
        ConfidenceState.HIGH,
        [replace(_evidence(), text_span="fabricated")],
    )
    with pytest.raises(CitationIntegrityError):
        build_citations(document, {"invoice_number": field})


def test_table_normalization_types_numbers() -> None:
    cells = (
        TableCell(0, 0, 0, 0, "Qty", 1, "e1"),
        TableCell(1, 1, 0, 0, "2", 1, "e2"),
    )
    table = normalize_table("d", "t", 1, cells)
    assert table.rows == ((Decimal("2"),),)
    assert table_to_json(table) == [{"Qty": Decimal("2")}]


def test_table_normalization_preserves_merged_flag() -> None:
    table = normalize_table("d", "t", 1, (TableCell(0, 0, 0, 1, "Header", 1, "e"),))
    assert table.merged_cells is True


def test_empty_table_normalizes_safely() -> None:
    assert normalize_table("d", "t", 1, ()).headers == ()


def test_privacy_detector_finds_email_and_credential() -> None:
    findings = detect_sensitive_text("a@example.com api_key=super-secret")
    assert {finding.category for finding in findings} == {"email", "credential"}


def test_privacy_redaction_removes_sensitive_values() -> None:
    redacted = redact_text("write to a@example.com")
    assert "a@example.com" not in redacted
    assert "[REDACTED:email]" in redacted


def test_sensitive_chunks_are_excluded() -> None:
    document = _document("Contact a@example.com", "Public paragraph")
    chunks = build_chunks(document)
    assert [chunk.text for chunk in chunks] == ["Public paragraph"]


def test_chunk_size_is_bounded() -> None:
    chunks = build_chunks(_document("x" * 140), max_characters=64)
    assert [chunk.character_size for chunk in chunks] == [64, 64, 12]


def test_audit_chain_detects_tampering() -> None:
    events = []
    append_audit_event(events, "one", {"document": "raw", "asset_id": "a"})
    append_audit_event(events, "two", {"status": "ok"})
    assert events[0].metadata["document"] == "[OMITTED]"
    assert verify_audit_chain(events)
    events[1] = replace(events[1], previous_hash="tampered")
    assert not verify_audit_chain(events)


def test_review_routing_catches_low_confidence() -> None:
    schema = ExtractionSchema(
        "s", "s", (DocumentType.GENERIC,), "1", (FieldDefinition("x", "string"),)
    )
    fields = {"x": ExtractedField("x", "v", "v", ConfidenceState.LOW, [_evidence()])}
    assert fields_requiring_review(schema, fields) == ("x",)


def test_review_correction_preserves_original() -> None:
    field = ExtractedField("x", "raw", "original", ConfidenceState.LOW, [_evidence()])
    decision = apply_review_decision(
        field, ReviewState.CORRECTED, reviewed_value="corrected", reason="verified"
    )
    assert decision.original_value == "original"
    assert field.effective_value == "corrected"


def test_profile_names_are_explicit() -> None:
    assert get_profile("ocr_only").force_ocr
    with pytest.raises(ValueError, match="Unknown"):
        get_profile("magic")


def test_docling_adapter_blocks_implicit_model_download() -> None:
    asset = validate_document("fixture.pdf", fixture_pdf(["plain"]))
    with pytest.raises(RuntimeError, match="artifacts_path"):
        DoclingParserAdapter().parse(asset, get_profile("balanced"))


def test_pipeline_config_bounds_retries() -> None:
    with pytest.raises(ValueError, match="bounded"):
        PipelineConfig(max_retries=4)


class _FlakyParser:
    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def parse(self, asset: object, profile: object) -> NormalizedDocument:
        self.calls += 1
        if self.calls == 1:
            raise RetryableProcessingFailure("temporary")
        return _document("plain")


def test_pipeline_retries_only_within_bound() -> None:
    parser = _FlakyParser()
    pipeline = DocuTracePipeline(
        parser=parser, config=PipelineConfig(parser_profile="fast", max_retries=1)
    )
    result = pipeline.process("fixture.pdf", fixture_pdf(["plain"]))
    assert parser.calls == 2
    assert result.metrics.attempts == 2


def test_pipeline_idempotency_returns_same_result() -> None:
    pipeline = DocuTracePipeline(config=PipelineConfig(parser_profile="fast"))
    payload = fixture_pdf(["plain"])
    first = pipeline.process("fixture.pdf", payload)
    second = pipeline.process("fixture.pdf", payload)
    assert first is second


def test_pipeline_rejects_unknown_schema() -> None:
    pipeline = DocuTracePipeline(config=PipelineConfig(parser_profile="fast"))
    with pytest.raises(ProcessingFailure, match="Unknown extraction schema"):
        pipeline.process("fixture.pdf", fixture_pdf(["plain"]), schema_id="missing")


def test_sensitive_field_is_redacted_in_export() -> None:
    schema = ExtractionSchema(
        "sample.contact.v1",
        "contact",
        (DocumentType.GENERIC,),
        "1",
        (FieldDefinition("email", "email", aliases=("email",), sensitive=True),),
    )
    pipeline = DocuTracePipeline(
        schemas=(schema,), config=PipelineConfig(parser_profile="fast")
    )
    result = pipeline.process(
        "fixture.pdf",
        fixture_pdf(["Email: user@example.com"]),
        schema_id=schema.schema_id,
    )
    exported = result_to_json(result)
    assert "user@example.com" not in exported
    assert "REDACTED" in exported


def test_exports_are_deterministic_and_readable() -> None:
    pipeline = DocuTracePipeline(config=PipelineConfig(parser_profile="fast"))
    result = pipeline.process("fixture.pdf", fixture_pdf(["plain"]))
    assert result_to_json(result) == result_to_json(result)
    assert "# DocuTrace result" in result_to_markdown(result)
    assert result.job.status == JobStatus.REVIEW_REQUIRED

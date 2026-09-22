# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

from __future__ import annotations

from decimal import Decimal

from docling.docutrace.adapters import fixture_pdf
from docling.docutrace.audit import verify_audit_chain
from docling.docutrace.evaluation import EvaluationCase, evaluate
from docling.docutrace.models import DocumentType, JobStatus
from docling.docutrace.pipeline import DocuTracePipeline, PipelineConfig


def _pipeline() -> DocuTracePipeline:
    return DocuTracePipeline(config=PipelineConfig(parser_profile="fast"))


def test_invoice_end_to_end_golden_case() -> None:
    payload = fixture_pdf(
        [
            "# Invoice",
            "Invoice Number: INV-100",
            "Invoice Date: 2026-09-01",
            "Due Date: 2026-09-30",
            "Vendor: Northwind",
            "Subtotal: 100.00",
            "Tax: 10.00",
            "Amount Due: 110.00",
            "Currency: USD",
            "| Description | Qty | Unit Price | Amount |",
            "| Widget | 2 | 50.00 | 100.00 |",
        ]
    )
    result = _pipeline().process("invoice.pdf", payload)
    evaluation = evaluate(
        result,
        EvaluationCase(
            "invoice-golden",
            DocumentType.INVOICE,
            {
                "invoice_number": "INV-100",
                "total": Decimal("110.00"),
                "currency": "USD",
            },
        ),
    )
    assert evaluation.passed
    assert result.job.status == JobStatus.COMPLETED
    assert result.tables[0].headers[0] == "Description"
    assert result.citations
    assert result.chunks
    assert verify_audit_chain(result.audit_events)
    assert result.provenance.input_fingerprint == result.asset.fingerprint


def test_contract_end_to_end_review_case() -> None:
    payload = fixture_pdf(
        [
            "# Services Agreement",
            "Agreement between Example Buyer and Example Vendor",
            "Parties: Example Buyer and Example Vendor",
            "Effective Date: 2026-09-01",
            "Termination Date: 2027-09-01",
            "Governing Law: New York",
            "Payment Terms: Net 30",
            "Renewal: Written agreement only",
        ]
    )
    result = _pipeline().process("contract.pdf", payload)
    evaluation = evaluate(
        result,
        EvaluationCase(
            "contract-golden",
            DocumentType.CONTRACT,
            {
                "effective_date": "2026-09-01",
                "governing_law": "New York",
            },
        ),
    )
    assert evaluation.passed
    assert result.job.status == JobStatus.COMPLETED
    assert result.classification.evidence

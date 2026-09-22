# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Parser adapters connecting governed processing to Docling output."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Protocol

from docling.docutrace.models import (
    BoundingBox,
    DocumentAsset,
    NormalizedDocument,
    NormalizedElement,
    NormalizedTable,
    TableCell,
)
from docling.docutrace.profiles import ProcessingProfile
from docling.docutrace.tables import normalize_table


class ParserAdapter(Protocol):
    name: str

    def parse(
        self, asset: DocumentAsset, profile: ProcessingProfile
    ) -> NormalizedDocument: ...


class DeterministicFixtureParser:
    """Small local parser for synthetic tests, examples, and offline CI.

    It accepts only documents containing the explicit ``DOCUTRACE-FIXTURE`` marker.
    It is not represented as a production PDF parser.
    """

    name = "deterministic_fixture_parser"

    def parse(
        self, asset: DocumentAsset, profile: ProcessingProfile
    ) -> NormalizedDocument:
        del profile
        decoded = asset.data.decode("utf-8", errors="ignore")
        if "DOCUTRACE-FIXTURE" not in decoded:
            raise ValueError(
                "The fixture parser accepts only marked synthetic fixtures"
            )
        lines = [
            line.strip(" \r\t%")
            for line in decoded.splitlines()
            if line.strip(" \r\t%")
            and not line.startswith("%PDF")
            and not line.startswith("%%EOF")
            and "/Type /Page" not in line
            and "DOCUTRACE-FIXTURE" not in line
        ]
        document_id = f"doc_{asset.fingerprint[:24]}"
        elements: list[NormalizedElement] = []
        table_lines: list[str] = []
        section: tuple[str, ...] = ()
        for index, line in enumerate(lines, start=1):
            if line.startswith("#"):
                section = (line.lstrip("# "),)
            element_id = f"el_{index:04d}"
            elements.append(
                NormalizedElement(
                    element_id=element_id,
                    page=1,
                    text=line,
                    label="table_row" if line.startswith("|") else "text",
                    bounding_box=BoundingBox(
                        0.0, float(index), 100.0, float(index + 1)
                    ),
                    section_path=section,
                )
            )
            if line.startswith("|") and line.endswith("|"):
                table_lines.append(line)
        tables: tuple[NormalizedTable, ...] = ()
        if len(table_lines) >= 2:
            cells: list[TableCell] = []
            element_by_text = {element.text: element for element in elements}
            for row_index, line in enumerate(table_lines):
                values = [value.strip() for value in line.strip("|").split("|")]
                element = element_by_text[line]
                for column_index, value in enumerate(values):
                    cells.append(
                        TableCell(
                            row_start=row_index,
                            row_end=row_index,
                            column_start=column_index,
                            column_end=column_index,
                            text=value,
                            page=1,
                            element_id=element.element_id,
                            bounding_box=element.bounding_box,
                        )
                    )
            tables = (normalize_table(document_id, "table_0001", 1, tuple(cells)),)
        return NormalizedDocument(
            document_id=document_id,
            filename=asset.filename,
            media_type=asset.media_type,
            page_count=asset.page_count,
            elements=tuple(elements),
            tables=tables,
            parser_backend=self.name,
        )


class DoclingParserAdapter:
    """In-memory, local-only adapter over the inherited Docling converter."""

    name = "docling_document_converter"

    def __init__(self, *, artifacts_path: Path | None = None) -> None:
        self.artifacts_path = artifacts_path

    def parse(
        self, asset: DocumentAsset, profile: ProcessingProfile
    ) -> NormalizedDocument:
        if (
            asset.media_type == "application/pdf"
            and (
                profile.enable_ocr or profile.enable_tables or profile.enable_enrichment
            )
            and self.artifacts_path is None
        ):
            raise RuntimeError(
                "Model-backed profiles require an explicit local artifacts_path; "
                "DocuTrace will not implicitly download model assets"
            )

        from docling_core.types.doc import TableItem, TextItem

        from docling.datamodel.base_models import DocumentStream, InputFormat
        from docling.datamodel.pipeline_options import (
            NativePdfPipelineOptions,
            PdfPipelineOptions,
        )
        from docling.document_converter import (
            DocumentConverter,
            NativePdfFormatOption,
            PdfFormatOption,
        )

        if asset.media_type == "application/pdf" and profile.name == "fast":
            native_options = NativePdfPipelineOptions(
                generate_picture_images=False,
                generate_page_images=False,
                enable_remote_services=False,
                allow_external_plugins=False,
                document_timeout=120.0,
            )
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: NativePdfFormatOption(
                        pipeline_options=native_options
                    )
                }
            )
        else:
            options = PdfPipelineOptions(
                do_ocr=profile.enable_ocr,
                do_table_structure=profile.enable_tables,
                do_code_enrichment=profile.enable_enrichment,
                do_formula_enrichment=profile.enable_enrichment,
                enable_remote_services=False,
                allow_external_plugins=False,
                artifacts_path=self.artifacts_path,
                document_timeout=120.0,
            )
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=options)
                }
            )
        stream = DocumentStream(name=asset.filename, stream=io.BytesIO(asset.data))
        result = converter.convert(
            stream,
            max_num_pages=asset.page_count,
            max_file_size=len(asset.data),
        )
        document_id = f"doc_{asset.fingerprint[:24]}"
        elements: list[NormalizedElement] = []
        tables: list[NormalizedTable] = []
        for index, (item, _level) in enumerate(
            result.document.iterate_items(), start=1
        ):
            element_id = f"el_{index:04d}"
            if isinstance(item, TextItem):
                provenance = item.prov[0] if item.prov else None
                box = None
                page = 1
                if provenance is not None:
                    page = provenance.page_no
                    box = BoundingBox(
                        provenance.bbox.l,
                        provenance.bbox.t,
                        provenance.bbox.r,
                        provenance.bbox.b,
                    )
                elements.append(
                    NormalizedElement(
                        element_id=element_id,
                        page=page,
                        text=item.text,
                        label=item.label.value,
                        bounding_box=box,
                    )
                )
            elif isinstance(item, TableItem):
                provenance = item.prov[0] if item.prov else None
                page = provenance.page_no if provenance is not None else 1
                box = None
                if provenance is not None:
                    box = BoundingBox(
                        provenance.bbox.l,
                        provenance.bbox.t,
                        provenance.bbox.r,
                        provenance.bbox.b,
                    )
                table_text = " | ".join(
                    cell.text for cell in item.data.table_cells if cell.text
                )
                elements.append(
                    NormalizedElement(
                        element_id=element_id,
                        page=page,
                        text=table_text,
                        label="table",
                        bounding_box=box,
                    )
                )
                cells = tuple(
                    TableCell(
                        row_start=cell.start_row_offset_idx,
                        row_end=max(
                            cell.start_row_offset_idx, cell.end_row_offset_idx - 1
                        ),
                        column_start=cell.start_col_offset_idx,
                        column_end=max(
                            cell.start_col_offset_idx, cell.end_col_offset_idx - 1
                        ),
                        text=cell.text,
                        page=page,
                        element_id=element_id,
                        bounding_box=box,
                    )
                    for cell in item.data.table_cells
                )
                tables.append(
                    normalize_table(
                        document_id, f"table_{len(tables) + 1:04d}", page, cells
                    )
                )
        return NormalizedDocument(
            document_id=document_id,
            filename=asset.filename,
            media_type=asset.media_type,
            page_count=asset.page_count,
            elements=tuple(elements),
            tables=tuple(tables),
            parser_backend=self.name,
            ocr_engine="configured_by_docling" if profile.enable_ocr else None,
            ocr_pages=tuple(range(1, asset.page_count + 1))
            if profile.force_ocr
            else (),
        )


def fixture_pdf(lines: list[str], *, pages: int = 1) -> bytes:
    """Build explicit non-production PDF-like bytes for deterministic tests."""

    page_markers = "\n".join("/Type /Page" for _ in range(pages))
    payload = "\n".join(lines)
    seed = uuid.uuid5(uuid.NAMESPACE_URL, payload).hex
    return (
        f"%PDF-1.4\n%DOCUTRACE-FIXTURE {seed}\n{page_markers}\n{payload}\n%%EOF\n"
    ).encode()

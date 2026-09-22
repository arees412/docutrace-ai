# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Controlled table normalization with row-level provenance."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from docling.docutrace.models import (
    EvidenceReference,
    NormalizedTable,
    TableCell,
)


def _typed_value(value: str) -> str | Decimal:
    cleaned = value.strip()
    candidate = (
        cleaned.replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    )
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", candidate):
        try:
            return Decimal(candidate)
        except InvalidOperation:
            pass
    return cleaned


def normalize_table(
    document_id: str, table_id: str, page: int, cells: tuple[TableCell, ...]
) -> NormalizedTable:
    if not cells:
        return NormalizedTable(table_id, page, (), (), (), ())
    row_count = max(cell.row_end for cell in cells) + 1
    column_count = max(cell.column_end for cell in cells) + 1
    matrix: list[list[str]] = [
        ["" for _ in range(column_count)] for _ in range(row_count)
    ]
    merged = False
    evidence_rows: list[list[EvidenceReference]] = [[] for _ in range(row_count)]
    for cell in cells:
        if cell.row_start < 0 or cell.column_start < 0:
            raise ValueError("Table offsets cannot be negative")
        if cell.row_end < cell.row_start or cell.column_end < cell.column_start:
            raise ValueError("Table cell span is inverted")
        merged = (
            merged
            or cell.row_end > cell.row_start
            or cell.column_end > cell.column_start
        )
        matrix[cell.row_start][cell.column_start] = cell.text.strip()
        evidence_rows[cell.row_start].append(
            EvidenceReference(
                document_id=document_id,
                page=cell.page,
                element_id=cell.element_id,
                text_span=cell.text,
                bounding_box=cell.bounding_box,
                extraction_method="table_cell",
            )
        )
    headers = tuple(
        value.strip() or f"column_{index + 1}" for index, value in enumerate(matrix[0])
    )
    rows = tuple(tuple(_typed_value(value) for value in row) for row in matrix[1:])
    return NormalizedTable(
        table_id=table_id,
        page=page,
        headers=headers,
        rows=rows,
        source_cells=cells,
        row_evidence=tuple(tuple(row) for row in evidence_rows[1:]),
        merged_cells=merged,
    )


def table_to_json(table: NormalizedTable) -> list[dict[str, object]]:
    return [dict(zip(table.headers, row)) for row in table.rows]

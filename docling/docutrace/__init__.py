# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Governed document-intelligence primitives built on Docling."""

from docling.docutrace.adapters import DoclingParserAdapter
from docling.docutrace.pipeline import DocuTracePipeline, PipelineConfig

__all__ = ["DoclingParserAdapter", "DocuTracePipeline", "PipelineConfig"]

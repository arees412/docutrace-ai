# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Bounded parser profiles without unsupported quality claims."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingProfile:
    name: str
    enable_ocr: bool
    enable_tables: bool
    enable_enrichment: bool
    force_ocr: bool = False


PROFILES: dict[str, ProcessingProfile] = {
    "fast": ProcessingProfile("fast", False, False, False),
    "balanced": ProcessingProfile("balanced", True, True, False),
    "high_accuracy": ProcessingProfile("high_accuracy", True, True, True),
    "ocr_only": ProcessingProfile("ocr_only", True, False, False, force_ocr=True),
}


def get_profile(name: str) -> ProcessingProfile:
    try:
        return PROFILES[name]
    except KeyError as error:
        supported = ", ".join(sorted(PROFILES))
        raise ValueError(
            f"Unknown parser profile {name!r}; choose one of: {supported}"
        ) from error

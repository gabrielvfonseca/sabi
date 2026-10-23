"""Shared utilities for the SABI extractor."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

CSV_FIELDS = [
    "name",
    "cif",
    "address",
    "city",
    "province",
    "postal_code",
    "phone",
    "activity",
    "detail_url",
]


def clean(text: str) -> str:
    """Collapse whitespace and strip surrounding whitespace."""
    return re.sub(r"\s+", " ", text or "").strip()


def record_to_row(record: Mapping, fields: Iterable[str] = CSV_FIELDS) -> dict:
    """Convert a record mapping to a CSV row dict limited to *fields*."""
    return {field: record.get(field, "") for field in fields}


def write_csv(
    records: Iterable[Mapping],
    path: str,
    fields: Iterable[str] = CSV_FIELDS,
) -> int:
    """Write records to a CSV file. Returns the number of rows written."""
    fields = list(fields)
    rows = [record_to_row(r, fields) for r in records]
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)

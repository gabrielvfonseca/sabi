"""Shared utilities for the SABI extractor."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .models import Record

CSV_FIELDS = [
    # Identity
    "name",
    "cif",
    "bvd_id",
    "legal_form",
    "incorporation_date",
    "status",
    # Contact
    "address",
    "city",
    "province",
    "postal_code",
    "country",
    "email",
    "phone",
    "website",
    # Activity
    "activity",
    "primary_cae",
    "secondary_cae",
    # Financials (latest)
    "latest_year",
    "revenue",
    "profit",
    "total_assets",
    "equity",
    "employees",
    "share_capital",
    # People (JSON)
    "directors",
    "auditors",
    # Ownership (JSON)
    "shareholders",
    "global_ultimate_owner",
    "subsidiaries",
    "group_companies_count",
    # Metadata
    "detail_url",
    "last_update",
    "consolidation_type",
    "available_years",
]


def clean(text: str) -> str:
    """Collapse whitespace and strip surrounding whitespace."""
    return re.sub(r"\s+", " ", text or "").strip()


def record_to_row(
    record: Mapping[str, Any],
    fields: Iterable[str] = CSV_FIELDS,
) -> dict[str, Any]:
    """Convert a record mapping to a CSV row dict limited to *fields*."""
    return {field: record.get(field, "") for field in fields}


def write_csv(
    records: Iterable[Record | Mapping[str, Any]],
    path: str,
    fields: Iterable[str] = CSV_FIELDS,
) -> int:
    """Write records to a CSV file. Returns the number of rows written."""
    fields = list(fields)
    rows: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, Record):
            rows.append(record.to_row())
        else:
            rows.append({field: record.get(field, "") for field in fields})
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)

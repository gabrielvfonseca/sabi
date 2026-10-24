"""Shared utilities for the SABI extractor."""

from __future__ import annotations

import csv
import json
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


def read_csv(path: str, fields: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Read a CSV file into a list of row dicts.

    JSON-encoded list fields (directors, auditors, shareholders, subsidiaries)
    are parsed back into Python lists when present.
    """
    fields = list(fields) if fields else None
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            row = {k: (v or "") for k, v in raw.items()}
            for key in ("directors", "auditors", "shareholders", "subsidiaries"):
                val = row.get(key)
                if val:
                    try:
                        row[key] = json.loads(val)
                    except (TypeError, json.JSONDecodeError):
                        row[key] = []
            rows.append(row)
    return rows


def to_json(records: Iterable[Record | Mapping[str, Any]]) -> str:
    """Serialize records to a JSON string (UTF-8, non-ASCII preserved)."""
    out = []
    for record in records:
        if isinstance(record, Record):
            out.append(record.to_row())
        else:
            out.append(dict(record))
    return json.dumps(out, ensure_ascii=False)


def list_fields() -> list[str]:
    """Return the canonical list of record field names."""
    return list(CSV_FIELDS)


def coerce_record(row: Mapping[str, Any]) -> Record:
    """Build a Record from a CSV/JSON row, coercing list/int fields.

    JSON-encoded list fields (directors, auditors, shareholders, subsidiaries)
    are parsed back into Python lists; numeric fields are coerced to int when
    possible.
    """
    data = {k: (v if v is not None else "") for k, v in row.items()}
    for key in ("directors", "auditors", "shareholders", "subsidiaries"):
        val = data.get(key)
        if isinstance(val, str):
            try:
                data[key] = json.loads(val)
            except (TypeError, json.JSONDecodeError):
                data[key] = []
        elif not isinstance(val, list):
            data[key] = []
    if "group_companies_count" in data:
        try:
            data["group_companies_count"] = int(data["group_companies_count"] or 0)
        except (TypeError, ValueError):
            data["group_companies_count"] = 0
    if "available_years" in data:
        try:
            data["available_years"] = int(data["available_years"] or 0)
        except (TypeError, ValueError):
            data["available_years"] = 0
    data.pop("extras", None)
    valid = {k: v for k, v in data.items() if k in Record.__dataclass_fields__}
    return Record(**valid)  # type: ignore[arg-type]

"""Data model for extracted company records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Record:
    """A single company record extracted from SABI Informa."""

    # Identity
    name: str = ""
    cif: str = ""
    bvd_id: str = ""
    legal_form: str = ""
    incorporation_date: str = ""
    status: str = ""

    # Contact
    address: str = ""
    city: str = ""
    province: str = ""
    postal_code: str = ""
    country: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""

    # Activity
    activity: str = ""
    primary_cae: str = ""
    secondary_cae: str = ""

    # Financials (latest year)
    latest_year: str = ""
    revenue: str = ""
    profit: str = ""
    total_assets: str = ""
    equity: str = ""
    employees: str = ""
    share_capital: str = ""

    # Financials (multi-year) - stored as JSON strings in extras
    financial_history: dict = field(default_factory=dict)
    ratios: dict = field(default_factory=dict)

    # People
    directors: list[dict] = field(default_factory=list)
    auditors: list[dict] = field(default_factory=list)

    # Ownership
    shareholders: list[dict] = field(default_factory=list)
    global_ultimate_owner: str = ""
    subsidiaries: list[dict] = field(default_factory=list)
    group_companies_count: int = 0

    # Metadata
    detail_url: str = ""
    last_update: str = ""
    consolidation_type: str = ""
    available_years: int = 0

    # Extras for any additional fields
    extras: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        row = asdict(self)
        # Flatten lists to JSON strings for CSV
        for key in ["directors", "auditors", "shareholders", "subsidiaries"]:
            val = row.get(key)
            if val:
                import json

                row[key] = json.dumps(val, ensure_ascii=False)
        row.pop("extras", None)
        row.update(self.extras)
        return row

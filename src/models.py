"""Data model for extracted company records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Record:
    """A single company record extracted from SABI Informa."""

    name: str = ""
    cif: str = ""
    address: str = ""
    city: str = ""
    province: str = ""
    postal_code: str = ""
    phone: str = ""
    activity: str = ""
    detail_url: str = ""
    extras: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        row = asdict(self)
        row.pop("extras", None)
        row.update(self.extras)
        return row

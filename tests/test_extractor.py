"""Tests for the SABI extractor package."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.embeddings import EmbeddingStore, _default_embedding
from src.extractor import SABIClient
from src.models import Record
from src.utils import clean, record_to_row, write_csv


class TestUtils(unittest.TestCase):
    def test_clean_collapses_whitespace(self):
        self.assertEqual(clean("  a   b  c  "), "a b c")
        self.assertEqual(clean(""), "")
        self.assertEqual(clean(None), "")

    def test_record_to_row_limits_fields(self):
        record = {"name": "Acme", "cif": "A1", "extra": "ignored"}
        row = record_to_row(record, fields=["name", "cif"])
        self.assertEqual(row, {"name": "Acme", "cif": "A1"})
        self.assertNotIn("extra", row)

    def test_write_csv(self):
        records = [
            {"name": "Acme", "cif": "A1", "city": "Madrid"},
            {"name": "Globex", "cif": "B2", "city": "Barcelona"},
        ]
        path = Path("/tmp/test_sabi_write.csv")
        try:
            n = write_csv(records, path, fields=["name", "cif", "city"])
            self.assertEqual(n, 2)
            content = path.read_text(encoding="utf-8")
            self.assertIn("name,cif,city", content)
            self.assertIn("Acme,A1,Madrid", content)
            self.assertIn("Globex,B2,Barcelona", content)
        finally:
            if path.exists():
                path.unlink()


class TestExtractor(unittest.TestCase):
    def setUp(self):
        self.html = (
            "<table>"
            "<tr class='record'>"
            "<td class='name'><a href='/company/1'>Acme SA</a></td>"
            "<td class='cif'>A12345678</td>"
            "<td class='city'>Madrid</td>"
            "</tr>"
            "<tr class='record'>"
            "<td class='name'><a href='/company/2'>Globex SL</a></td>"
            "<td class='cif'>B87654321</td>"
            "<td class='city'>Barcelona</td>"
            "</tr>"
            "</table>"
            "<a class='next' href='?page=2'>Next</a>"
        )
        self.client = SABIClient()

    def test_parse_search_page(self):
        result = self.client._parse_search_page(
            self.html, "https://sabi.informa.es/search", 1
        )
        self.assertEqual(len(result.records), 2)
        self.assertTrue(result.has_next)
        self.assertEqual(result.records[0].name, "Acme SA")
        self.assertEqual(result.records[0].cif, "A12345678")
        self.assertEqual(result.records[0].city, "Madrid")
        self.assertEqual(
            result.records[0].detail_url,
            "https://sabi.informa.es/company/1",
        )

    def test_login_form_discovery(self):
        html = (
            '<form id="LoginForm" action="/R1/SabiInforma/SignIn" method="post">'
            '<input name="__RequestVerificationToken" value="TOKEN123" />'
            '<input name="user" />'
            "</form>"
        )
        action, token = self.client._discover_login_form(html)
        self.assertEqual(action, "https://sabi.informa.es/R1/SabiInforma/SignIn")
        self.assertEqual(token, "TOKEN123")


class TestEmbeddings(unittest.TestCase):
    def test_default_embedding_deterministic(self):
        a = _default_embedding("hello world")
        b = _default_embedding("hello world")
        c = _default_embedding("different text")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(len(a), 384)

    def test_store_upsert_and_search(self):
        store = EmbeddingStore(db_path=":memory:", embedding_dim=8)
        try:
            store.upsert(
                Record(
                    name="Acme SA",
                    cif="A1",
                    city="Madrid",
                    activity="Software",
                )
            )
            store.upsert(
                Record(
                    name="Globex SL",
                    cif="B2",
                    city="Barcelona",
                    activity="Consulting",
                )
            )
            all_records = store.all()
            self.assertEqual(len(all_records), 2)

            # Upserting same CIF should replace, not duplicate.
            store.upsert(
                Record(
                    name="Acme SA Updated",
                    cif="A1",
                    city="Madrid",
                    activity="Software",
                )
            )
            all_records = store.all()
            self.assertEqual(len(all_records), 2)

            results = store.search_similar("software", limit=5)
            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0]["cif"], "A1")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()

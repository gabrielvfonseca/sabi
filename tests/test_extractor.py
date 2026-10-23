"""Tests for the SABI extractor package."""

from __future__ import annotations

import re
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
        self.client = SABIClient()

    def test_company_name_detection(self):
        """Test company name detection with various suffixes."""
        self.assertTrue(self.client._is_company_name("ACME SA"))
        self.assertTrue(self.client._is_company_name("Globex SL"))
        self.assertTrue(self.client._is_company_name("Company LTD"))
        self.assertTrue(self.client._is_company_name("Firm GmbH"))
        self.assertTrue(self.client._is_company_name("CVJF - DESIGN E ARQUITETURA, LDA"))
        self.assertTrue(self.client._is_company_name("SANTANDER GLOBAL TECHNOLOGY AND OPERATIONS SLU"))
        
        # Should reject non-company names
        self.assertFalse(self.client._is_company_name("Cancelar"))
        self.assertFalse(self.client._is_company_name("Nombre de la empresa"))
        self.assertFalse(self.client._is_company_name("Exportar"))
        self.assertFalse(self.client._is_company_name("2.900.000 Spanish"))
        self.assertFalse(self.client._is_company_name("12345"))

    def test_address_line_detection(self):
        """Test address line detection."""
        self.assertTrue(self.client._is_address_line("28660 BOADILLA DEL MONTE (MADRID, ESPANA)Empresa privadaCódigo NIF"))
        self.assertTrue(self.client._is_address_line("2755-067 Alcabideche (LISBOA, PORTUGAL)Empresa privadaCódigo NIF"))
        self.assertFalse(self.client._is_address_line("Just a regular line"))
        self.assertFalse(self.client._is_address_line("No postal code here"))

    def test_parse_address_components(self):
        """Test address component extraction."""
        record = Record(
            address="28660 BOADILLA DEL MONTE (MADRID, ESPANA)Empresa privadaCódigo NIF"
        )
        self.client._parse_address_components(record)
        self.assertEqual(record.postal_code, "28660")
        self.assertEqual(record.city, "BOADILLA DEL MONTE")
        self.assertEqual(record.country, "ESPANA")

        record2 = Record(
            address="PRACETA À RUA DA ESCOLA, 105 - ALVIDE | 2755-067 Alcabideche | LISBOA | PORTUGAL"
        )
        self.client._parse_address_components(record2)
        self.assertEqual(record2.postal_code, "2755-067")
        self.assertEqual(record2.city, "Alcabideche")
        self.assertEqual(record2.country, "PORTUGAL")

    def test_cif_extraction(self):
        """Test CIF extraction from concatenated lines."""
        line = "2755-067 Alcabideche (LISBOA, PORTUGAL)Empresa privadaCódigo NIF514737964Fecha últimas cuentas31/12/2025"
        match = re.search(r"Código NIF\s*([A-Z0-9]+)", line)
        self.assertIsNotNone(match)
        cif = match.group(1)
        # Remove trailing letter
        if len(cif) > 9 and cif[-1].isalpha():
            cif = cif[:-1]
        self.assertEqual(cif, "514737964")


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
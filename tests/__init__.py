"""Tests for the SABI extractor package (package entry point)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.embeddings import EmbeddingStore  # noqa: F401
from src.extractor import SABIClient  # noqa: F401
from src.models import Record  # noqa: F401
from src.utils import clean, write_csv  # noqa: F401


class TestImports(unittest.TestCase):
    def test_modules_importable(self):
        self.assertIsNotNone(SABIClient)
        self.assertIsNotNone(EmbeddingStore)
        self.assertIsNotNone(clean)
        self.assertIsNotNone(write_csv)
        self.assertIsNotNone(Record)


if __name__ == "__main__":
    unittest.main()

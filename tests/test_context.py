import tempfile
import unittest
from pathlib import Path

from src.context import ContextBuilder


class TestContextStep(unittest.TestCase):
    def test_augment_tender_does_not_crash_when_scope_match_is_numeric(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "state").mkdir(parents=True, exist_ok=True)
            (root / "config" / "civils_niche.yaml").write_text(
                "trades:\n  civils:\n    keywords:\n      - drainage\n",
                encoding="utf-8",
            )
            (root / "state" / "buyer_profiles.json").write_text("{}", encoding="utf-8")

            builder = ContextBuilder(root / "config", root / "state")
            tender = {
                "title": "Drainage package",
                "description": "Drainage and civils works",
                "buyer_name": "Buyer A",
                "score": 55,
                "score_breakdown": {"value": 20},
            }

            augmented = builder.augment_tender(tender)

            self.assertIn("context", augmented)
            self.assertIn("narrative", augmented["context"])
            self.assertTrue(augmented["context"]["narrative"])


if __name__ == "__main__":
    unittest.main()

import unittest

from agent_rfq_extractor.quality import normalize_items


class TTCleanupTests(unittest.TestCase):
    def test_construction_glass_type_is_not_tt(self):
        unit = self._unit(
            {
                "TT": "monolithic",
                "color": "bronze",
                "field_sources": {"TT": "body", "color": "body"},
            }
        )

        self.assertNotIn("TT", unit["glass_specs"])
        self.assertEqual(unit["glass_specs"]["color"], "bronze")
        self.assertNotIn("source", unit)
        self.assertNotIn("field_sources", unit)

    def test_monolithic_color_only_tt_moves_to_color(self):
        unit = self._unit({"TT": "bronze", "field_sources": {"TT": "body"}})

        self.assertNotIn("TT", unit["glass_specs"])
        self.assertEqual(unit["glass_specs"]["color"], "bronze")

    def test_spandrel_tt_survives_with_color(self):
        unit = self._unit({"TT": "spandrel", "color": "warm grey"})

        self.assertEqual(unit["glass_specs"]["TT"], "spandrel")
        self.assertEqual(unit["glass_specs"]["color"], "warm grey")

    def test_note_examples_do_not_infer_spandrel(self):
        unit = self._unit(
            {
                "color": "bronze",
                "notes": (
                    "Bronze is a tint color placed in color field; TT left null as "
                    "no separate finish type (e.g. spandrel, mirror) was stated."
                ),
            }
        )

        self.assertNotIn("TT", unit["glass_specs"])
        self.assertEqual(unit["glass_specs"]["color"], "bronze")

    def _unit(self, overrides):
        raw = {
            "dimensions": "71 1/2 x 99 5/8",
            "quantity": 1,
            "shape": "rectangle",
            "glass_type": "monolithic",
            "TK": '1/4"',
            "HT": "tempered",
        }
        raw.update(overrides)
        return normalize_items([raw])[0].to_glass_unit()


if __name__ == "__main__":
    unittest.main()

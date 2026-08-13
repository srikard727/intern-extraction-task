import unittest

from agent_rfq_extractor.units import (
    normalize_measurement,
    normalize_quantity,
    split_dimension_pair,
)


class UnitNormalizationTests(unittest.TestCase):
    def test_supported_units_normalize_to_decimal_inches(self):
        cases = {
            "600mm": 23.622,
            "150cm": 59.0551,
            "1m": 39.3701,
            "5 ft": 60.0,
            '24 1/2"': 24.5,
            '19-7/8"': 19.875,
            "43¾": 43.75,
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_measurement(raw), expected)

    def test_architectural_feet_and_inches_are_combined(self):
        self.assertEqual(normalize_measurement("5' 6\""), 66.0)
        self.assertEqual(normalize_measurement("5'-6 1/2\""), 66.5)

        pair = split_dimension_pair("5'-6 1/2\" x 7'-2\"")
        self.assertEqual(pair, ("5'-6 1/2\"", "7'-2\""))
        self.assertEqual(tuple(normalize_measurement(value) for value in pair), (66.5, 86.0))

    def test_area_is_not_treated_as_a_dimension(self):
        self.assertIsNone(normalize_measurement("120 square feet"))

    def test_ambiguous_quantity_is_not_promoted_to_a_definite_count(self):
        for raw in ("around 20", "between 6 and 8", "several", "roughly fifteen"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_quantity(raw))


if __name__ == "__main__":
    unittest.main()

import unittest

from agent_rfq_extractor.quality import build_review, normalize_items


class QualityRuleTests(unittest.TestCase):
    def test_monolithic_preserves_clear_tt_and_source(self):
        item = normalize_items(
            [
                {
                    "dimensions": '24" x 36"',
                    "quantity": 2,
                    "glass_type": "monolithic",
                    "TK": '1/4"',
                    "HT": "tempered",
                    "color": "clear",
                    "source": "body",
                    "field_sources": {"color": "body"},
                }
            ]
        )[0]

        unit = item.to_glass_unit()
        self.assertEqual(unit["glass_specs"]["TT"], "clear")
        self.assertEqual(item.field_sources["TT"], "body")
        self.assertEqual(item.missing_fields, [])

    def test_mirror_does_not_require_heat_treatment(self):
        item = normalize_items(
            [
                {
                    "dimensions": '60" x 84"',
                    "glass_type": "monolithic",
                    "TK": '1/4"',
                    "TT": "mirror",
                }
            ]
        )[0]

        self.assertNotIn("HT", item.missing_fields)
        self.assertIsNone(build_review([item]))

    def test_required_fields_vary_by_glass_type(self):
        cases = {
            "monolithic": ["TK", "HT"],
            "laminated": [
                "TK1",
                "TK2",
                "interlayer_thickness",
                "interlayer_material",
                "HT1",
                "HT2",
            ],
            "insulated": [
                "TK1",
                "TK2",
                "spacer_material",
                "spacer_thickness",
                "HT1",
                "HT2",
            ],
            "laminated-insulated": [
                "TK1",
                "TK2",
                "TK3",
                "HT1",
                "HT2",
                "HT3",
                "interlayer_material",
                "interlayer_thickness",
                "spacer_material",
                "spacer_thickness",
                "laminate_lite",
            ],
        }

        for glass_type, expected_missing in cases.items():
            with self.subTest(glass_type=glass_type):
                item = normalize_items(
                    [{"dimensions": '24" x 36"', "glass_type": glass_type}]
                )[0]
                self.assertEqual(item.missing_fields, expected_missing)

    def test_specific_multi_lite_color_replaces_generic_tinted_label(self):
        item = normalize_items(
            [
                {
                    "dimensions": '48" x 96"',
                    "glass_type": "laminated",
                    "TT1": "tinted",
                    "TT2": "tinted",
                    "color": "grey",
                    "field_sources": {
                        "TT1": "body",
                        "TT2": "body",
                        "color": "body",
                    },
                }
            ]
        )[0]

        specs = item.to_glass_unit()["glass_specs"]
        self.assertEqual(specs["TT1"], "grey")
        self.assertEqual(specs["TT2"], "grey")

    def test_fabrication_details_are_structured_separately_from_edge_work(self):
        item = normalize_items(
            [
                {
                    "dimensions": '36" x 84"',
                    "glass_type": "monolithic",
                    "TK": '1/2"',
                    "HT": "tempered",
                    "TT": "clear",
                    "edge_work": "flat polished",
                    "fabrication_details": 'two 1" pull holes',
                }
            ]
        )[0]

        self.assertEqual(
            item.to_glass_unit()["fabrication"],
            {"edge_work": "flat polished", "details": 'two 1" pull holes'},
        )

    def test_fabrication_details_are_recovered_from_grounded_notes(self):
        item = normalize_items(
            [
                {
                    "dimensions": '36" x 84"',
                    "glass_type": "monolithic",
                    "TK": '3/8"',
                    "HT": "tempered",
                    "notes": (
                        'Two 1" pull holes ~4" down from each top corner. '
                        "Budgetary pricing requested."
                    ),
                }
            ]
        )[0]

        self.assertEqual(
            item.fabrication_details,
            'Two 1" pull holes ~4" down from each top corner.',
        )
        review = build_review([item])
        self.assertIsNotNone(review)
        self.assertIn("Fabrication details are approximate", review.reason)

    def test_complete_fabrication_detail_does_not_force_review(self):
        item = normalize_items(
            [
                {
                    "dimensions": '60" x 84"',
                    "glass_type": "monolithic",
                    "TK": '1/4"',
                    "TT": "mirror",
                    "notes": "Safety backing (vinyl) requested on back for gym wall install.",
                }
            ]
        )[0]

        self.assertEqual(
            item.fabrication_details,
            "Safety backing (vinyl) requested on back for gym wall install.",
        )
        self.assertIsNone(build_review([item]))

    def test_approximate_integer_quantity_defaults_to_one(self):
        item = normalize_items(
            [
                {
                    "dimensions": '48" x 96"',
                    "quantity": 20,
                    "glass_type": "monolithic",
                    "TK": '1/4"',
                    "HT": "tempered",
                    "notes": "Quantity ~20, could increase after field verification.",
                }
            ]
        )[0]

        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.field_sources["quantity"], "default")
        self.assertIn("pending confirmation", item.notes)

    def test_body_attachment_conflict_always_requires_review(self):
        item = normalize_items(
            [
                {
                    "dimensions": '24" x 36"',
                    "glass_type": "monolithic",
                    "TK": '3/8"',
                    "HT": "tempered",
                }
            ]
        )[0]
        review = build_review(
            [item],
            {
                "reason": None,
                "conflicts": [
                    {
                        "field": "TK",
                        "body": '1/4"',
                        "attachment": '3/8"',
                        "source": "attachment:drawing.pdf",
                    }
                ],
            },
        )

        self.assertIsNotNone(review)
        self.assertEqual(len(review.conflicts), 1)
        self.assertIn("conflicts require review", review.reason)


if __name__ == "__main__":
    unittest.main()

import unittest

from agent_rfq_extractor.graph import RFQExtractionGraph
from agent_rfq_extractor.models import InboundEmail, extraction_payload
from agent_rfq_extractor.pipeline import parse_fixture
from agent_rfq_extractor.quality import build_review, normalize_items


class FakeExtractor:
    model = "fake-model"

    def __init__(self, payload):
        self.payload = payload

    def extract(self, email):
        return self.payload


class FixtureExtractionLogicTests(unittest.TestCase):
    def test_parse_fixture_loads_all_provided_emails(self):
        emails = parse_fixture("Emails.txt")

        self.assertEqual(len(emails), 28)
        self.assertEqual(emails[0].email_id, "fixture-001")
        self.assertEqual(emails[-1].email_id, "fixture-028")

    def test_graph_classifies_and_extracts_monolithic_fixture_payload(self):
        graph = RFQExtractionGraph(
            FakeExtractor(
                {
                    "items": [
                        {
                            "mark": "GL-101",
                            "dimensions": '48" x 96"',
                            "quantity": 4,
                            "glass_type": "monolithic",
                            "TK": '1/2"',
                            "HT": "tempered",
                            "edge_work": "flat polish all edges",
                        }
                    ],
                    "review": {"reason": None, "conflicts": []},
                }
            )
        )
        email = InboundEmail(
            email_id="fixture-test-001",
            conv_id="fixture-test-thread-001",
            body_text='Please quote GL-101: Qty 4, 48" x 96", 1/2" clear tempered.',
            has_attachments=False,
        )

        record = graph.process_email(email)
        unit = record.to_jsonable()["extraction"]["glass_type_groups"][0]["glass_units"][0]

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.llm_model, "fake-model")
        self.assertEqual(record.items[0].glass_type, "monolithic")
        self.assertEqual(unit["quantity"], 4)
        self.assertEqual(unit["width"], 48.0)
        self.assertEqual(unit["height"], 96.0)
        self.assertEqual(unit["glass_specs"]["TK"], '1/2"')
        self.assertEqual(unit["glass_specs"]["HT"], "tempered")

    def test_mixed_package_groups_by_glass_type(self):
        items = normalize_items(
            [
                {
                    "dimensions": '48" x 96"',
                    "quantity": 2,
                    "glass_type": "monolithic",
                    "TK": '1/2"',
                    "HT": "tempered",
                },
                {
                    "dimensions": '60" x 120"',
                    "quantity": 1,
                    "glass_type": "laminated",
                    "construction": '1/4" clear HS + .060 PVB + 1/4" clear HS',
                },
                {
                    "dimensions": '36" x 72"',
                    "quantity": 4,
                    "glass_type": "insulated",
                    "construction": '1/4" clear HS / 1/2" airspace / 1/4" clear HS',
                    "gas_fill": "argon",
                },
                {
                    "dimensions": '48" x 96"',
                    "quantity": 2,
                    "glass_type": "laminated-insulated",
                    "construction": (
                        'Outboard 1/4" + .090 PVB + 1/4", '
                        '1/2" airspace, inboard 1/4" HS'
                    ),
                    "interlayer_material": "PVB",
                    "interlayer_thickness": '.090"',
                    "laminated_lite": "outboard",
                },
            ]
        )

        payload = extraction_payload(items)

        self.assertEqual(payload["glass_type"], "mixed")
        self.assertEqual(
            payload["glass_types"],
            ["monolithic", "laminated", "insulated", "laminated-insulated"],
        )
        self.assertEqual(len(payload["glass_type_groups"]), 4)
        self.assertEqual(payload["glass_type_groups"][1]["glass_units"][0]["glass_specs"]["HT1"], "heat strengthened")
        self.assertEqual(payload["glass_type_groups"][2]["glass_units"][0]["glass_specs"]["spacer_thickness"], '1/2"')

    def test_area_only_request_requires_review_without_dimensions(self):
        items = normalize_items(
            [
                {
                    "dimensions": "120 square feet",
                    "quantity": None,
                    "glass_type": "monolithic",
                    "TK": '1/2"',
                    "HT": "tempered",
                    "edge_work": "flat polished",
                }
            ]
        )

        review = build_review(items)

        self.assertIsNotNone(review)
        self.assertEqual(items[0].dimensions, None)
        self.assertIn("dimensions", items[0].missing_fields)
        self.assertEqual(items[0].quantity, 1)

    def test_insulated_outboard_color_exports_as_lite_tt(self):
        item = normalize_items(
            [
                {
                    "dimensions": "72 x 84",
                    "quantity": 1,
                    "glass_type": "insulated",
                    "HT1": "tempered",
                    "HT2": "tempered",
                    "TT2": "clear",
                    "color": "bronze",
                    "notes": "Outboard lite bronze, inboard lite clear, tempered both sides.",
                }
            ]
        )[0]

        specs = item.to_glass_unit()["glass_specs"]

        self.assertEqual(specs["TT1"], "bronze")
        self.assertEqual(specs["TT2"], "clear")

    def test_liu_keeps_explicit_inboard_heat_treatment(self):
        item = normalize_items(
            [
                {
                    "dimensions": "48 x 96",
                    "quantity": 2,
                    "glass_type": "laminated-insulated",
                    "TK1": '1/4"',
                    "TK2": '1/4"',
                    "TK3": '1/4"',
                    "HT3": "heat strengthened",
                    "interlayer_material": "PVB",
                    "interlayer_thickness": '.090"',
                    "spacer_thickness": '1/2"',
                    "gas_fill": "argon",
                    "laminated_lite": "outboard",
                    "notes": (
                        'Outboard 1/4" + .090 PVB + 1/4", 1/2" airspace, '
                        'inboard 1/4" HS. Outboard laminated plies heat treatment '
                        "not specified; not inheriting inboard HS."
                    ),
                }
            ]
        )[0]

        specs = item.to_glass_unit()["glass_specs"]

        self.assertIsNone(specs["HT1"])
        self.assertIsNone(specs["HT2"])
        self.assertEqual(specs["HT3"], "heat strengthened")
        self.assertNotIn("HT3", item.missing_fields)


if __name__ == "__main__":
    unittest.main()

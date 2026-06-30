import unittest

from helpers.PATARules import PATARules


class TestPATARules(unittest.TestCase):
    def test_voucher_null_does_not_mark_other(self):
        response = {
            "data": {
                "voucher": None,
                "positions": [{"state": "SHIPPED", "sellingPrice": 1000}],
            }
        }

        self.assertEqual(
            PATARules.calculate_action_reason_and_amount(response),
            (None, None),
        )

    def test_non_null_voucher_marks_order_as_other(self):
        response = {
            "data": {
                "voucher": {"amount": 4190,
                            "code": "TREAT20",
                            "createdAt": "2025-12-30T06:18:19+00:00",
                            "updatedAt": "2025-12-30T06:18:19+00:00"},
                "positions": [{"state": "SHIPPED", "sellingPrice": 1000}],
            }
        }

        self.assertEqual(
            PATARules.calculate_action_reason_and_amount(response),
            ("OTHER", 0),
        )

    def test_ignored_voucher_prefix_does_not_mark_order_as_other(self):
        response = {
            "data": {
                "voucher": {"code": "MiintoStud123"},
                "positions": [{"state": "SHIPPED", "sellingPrice": 1000}],
            }
        }

        self.assertEqual(
            PATARules.calculate_action_reason_and_amount(response),
            (None, None),
        )

    def test_fraud_internal_note_marks_order_as_other(self):
        response = {
            "data": {
                "events": [
                    {
                        "accessorIdentifier": "PATA-Legacy",
                        "createdAt": "2025-12-30T06:18:20+01:00",
                        "message": "Customer has fraud risk. Do not refund.",
                        "type": "internal note"

                    }
                ],
                "positions": [{"state": "SHIPPED", "sellingPrice": 1000}],
            }
        }

        self.assertEqual(
            PATARules.calculate_action_reason_and_amount(response),
            ("OTHER", 0),
        )

    def test_fraud_keyword_in_non_internal_note_is_ignored(self):
        response = {
            "data": {
                "events": [{"type": "customer note", "message": "fraud risk"}],
                "positions": [{"state": "SHIPPED", "sellingPrice": 1000}],
            }
        }

        self.assertEqual(
            PATARules.calculate_action_reason_and_amount(response),
            (None, None),
        )

    def test_fully_returned_order_marks_item_returned(self):
        response = {
            "data": {
                "positions": [
                    {
                        "state": "SHIPPED",
                        "sellingPrice": 1000,
                        "rma": {
                            "cases": [
                                {"positions": [{"status": "RETURNED"}]},
                            ]
                        },
                    },
                    {"state": "REJECTED", "sellingPrice": 2000},
                ]
            }
        }

        self.assertEqual(
            PATARules.calculate_action_reason_and_amount(response),
            ("ITEM_RETURNED", 0),
        )

    def test_partial_return_marks_order_update_with_kept_position_amount(self):
        response = {
            "data": {

                "id": "test-order-123",

                "positions": [
                    {
                        "state": "SHIPPED",
                        "id": "688550",
                        "sellingPrice": 8450
                    },
                    {
                        "state": "SHIPPED",
                        "id": "688551",
                        "sellingPrice": 12500
                    }
                ],

                "rma": {
                    "cases": [
                        {
                            "id": "88576",
                            "positions": [
                                {
                                    "id": "688550",
                                    "status": "RETURNED",
                                    "returnPriceGross": 8450
                                }
                            ]

                        }
                    ],
                    "eligibility": {
                        "positions": [
                            {
                                "id": "688550",
                                "eligibleForRma": False,
                                "sellingPriceGross": 8450
                            },
                            {
                                "id": "688551",
                                "eligibleForRma": False,
                                "sellingPriceGross": 12500
                            }
                        ]
                    }
                }
            }
        }

        self.assertEqual(
                PATARules.calculate_action_reason_and_amount(response),
                ("ORDER_UPDATE", 125),
            )

    def test_pending_position_marks_order_as_other(self):
        response = {
                "data": {
                    "positions": [
                        {"state": "ACTIVE", "sellingPrice": 1000}

                    ]
                }
            }

        self.assertEqual(
                PATARules.calculate_action_reason_and_amount(response),
                ("OTHER", 0),
            )

    def test_fully_shipped_order_without_rma_returns_no_action(self):
        response = {
                "data": {
                    "positions": [
                        {"state": "SHIPPED", "sellingPrice": 1000},
                        {"state": "SHIPPED", "sellingPrice": 2000},
                    ]
                }
            }

        self.assertEqual(
                PATARules.calculate_action_reason_and_amount(response),
                (None, None),
            )

    def test_no_positions_marks_order_as_other(self):
        response = {"data": {"positions": []}}

        self.assertEqual(
                PATARules.calculate_action_reason_and_amount(response),
                ("OTHER", 0),
            )

if __name__ == "__main__":
        unittest.main()
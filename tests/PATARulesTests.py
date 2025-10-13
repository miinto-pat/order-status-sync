import pytest
from helpers import PATARules


# -----------------------------
# Tests for has_voucher_code
# -----------------------------
@pytest.mark.parametrize(
    "response,expected",
    [
        ({"voucher": {"code": "ABC123"}}, True),
        ({"voucher": {"code": "  XYZ  "}}, True),
        ({"voucher": {"code": ""}}, False),
        ({"voucher": {"code": None}}, False),
        ({"voucher": {}}, False),
        ({}, False),
        ({"voucher": None}, False),
    ]
)
def test_has_voucher_code(response, expected):
    assert PATARules.PATARules.has_voucher_code(response) is expected


# -----------------------------
# Tests for calculate_action_reason_and_amount
# -----------------------------
def make_position(status, amount, price_amount=None):
    return {
        "status": status,
        "amount": amount,
        "price": {"amount": price_amount} if price_amount is not None else None
    }


def test_calculate_with_voucher_returns_other():
    response = {"data": {"voucher": {"code": "V123"}, "positions": []}}
    reason, amount = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "OTHER" and amount == 0


def test_calculate_with_pending_position_returns_other():
    response = {
        "data": {
            "positions": [
                make_position("pending", 1)
            ]
        }
    }
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "OTHER" and cost == 0

def test_calculate_with_pending_multiple_position_returns_order_update():
    response = {
        "data": {
            "positions": [
                make_position("pending", 1),
                make_position("sent", 1, price_amount=50000)
            ]
        }
    }
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "ORDER_UPDATE" and cost ==500

def test_calculate_with_pending_multiple_position_returns_item_returned():
    response = {
        "data": {
            "positions": [
                make_position("pending", 1),
                make_position("sent", 0, price_amount=50000)
            ]
        }
    }
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "ITEM_RETURNED" and cost ==0

def test_calculate_with_pending_multiple_position_returns_item_returned_rejected_0():
    response = {
        "data": {
            "positions": [
                make_position("pending", 1),
                make_position("rejected", 1, price_amount=50000)
            ]
        }
    }
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "ITEM_RETURNED" and cost ==0

def test_calculate_fully_returned_rejected_1():
    response = {
        "data": {
            "positions": [
                make_position("rejected", 1)

            ]
        }
    }
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "ITEM_RETURNED" and cost == 0

def test_calculate_fully_returned_accepted_0():
    response = {
        "data": {
            "positions": [
                make_position("accepted", 0)

            ]
        }
    }
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "ITEM_RETURNED" and cost == 0

def test_calculate_fully_returned_sent_0():
    response = {
        "data": {
            "positions": [
                make_position("sent", 0)

            ]
        }
    }
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "ITEM_RETURNED" and cost == 0

def test_calculate_fully_returned_multiple_positions():
    # Multiple positions, all either rejected (amount=1) or returned (amount=0, status=accepted/sent)
    response = {
        "data": {
            "positions": [
                make_position("rejected", 1, 15100),
                make_position("accepted", 0, 36000),
                make_position("sent", 0, 20000)
            ]
        }
    }

    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)

    assert reason == "ITEM_RETURNED"
    assert cost == 0

def test_calculate_partial_return_returns_order_update():
    # One position refunded (amount 53000), one not refunded (amount 3900)
    response = {
        "data": {
            "positions": [
                make_position("accepted", 0, 53000),  # refunded/returned
                make_position("sent", 1, 3900),       # not refunded
            ]
        }
    }

    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)

    assert reason == "ORDER_UPDATE"
    assert cost == 39


def test_calculate_fully_processed_returns_none():
    response = {
        "data": {
            "positions": [
                make_position("accepted", 1),
                make_position("sent", 1)
            ]
        }
    }
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason is None and cost is None


def test_calculate_no_positions_returns_other():
    response = {"data": {"positions": []}}
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "OTHER" and cost == 0


def test_calculate_handles_missing_data_key():
    response = {}  # no "data" key
    reason, cost = PATARules.PATARules.calculate_action_reason_and_amount(response)
    assert reason == "OTHER" and cost == 0

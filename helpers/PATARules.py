from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


class PATARules:
    FRAUD_KEYWORDS = (
        "fraud risk",
        "fraud order",
        "do not refund",
        "do not issue refund",
        "declined rma process",
        "lost parcels process",
    )

    IGNORED_VOUCHER_PREFIXES = (
        "MiintoStud",
        "Alumni",
        "MCMiinto",
        "StuMiinto",
        "RBTT",
    )

    PENDING_STATES = {"CREATED", "ACTIVE", "ACCEPTED"}
    RETURNED_STATUS = "RETURNED"
    REJECTED_STATE = "REJECTED"
    SHIPPED_STATE = "SHIPPED"

    @staticmethod
    def has_voucher_code(order_data: dict[str, Any]) -> bool:
        """Return True when a non-ignored voucher code is present."""
        voucher = order_data.get("voucher")
        if not voucher:
            return False

        if not isinstance(voucher, dict):
            return True

        code = str(voucher.get("code") or "").strip()
        if not code:
            return False

        return not any(prefix in code for prefix in PATARules.IGNORED_VOUCHER_PREFIXES)

    @staticmethod
    def detect_fraud(response: dict[str, Any]) -> bool:
        """Return True if an internal note contains a fraud/do-not-refund keyword."""
        events = response.get("data", {}).get("events") or []

        for event in events:
            if not isinstance(event, dict):
                continue

            note_type = str(event.get("type") or "").lower()
            if note_type != "internal note":
                continue

            message = str(event.get("message") or "").lower()
            if any(keyword in message for keyword in PATARules.FRAUD_KEYWORDS):
                logger.warning("Fraud/do-not-refund detected in internal note: %s", message)
                return True

        return False

    @staticmethod
    def _get_returned_position_ids(order_data: dict[str, Any]) -> set[str]:
        """Return order position IDs that appear in order-level RMA as RETURNED."""
        returned_ids: set[str] = set()
        rma = order_data.get("rma") or {}

        for case in rma.get("cases") or []:
            for rma_position in case.get("positions") or []:
                status = str(rma_position.get("status") or "").upper()
                if status != PATARules.RETURNED_STATUS:
                    continue

                position_id = rma_position.get("id") or rma_position.get("positionId") or rma_position.get("orderPositionId")
                if position_id:
                    returned_ids.add(str(position_id))

        return returned_ids

    @staticmethod
    def _is_position_returned(position: dict[str, Any], returned_position_ids: set[str] | None = None) -> bool:
        """Return True if any RMA position has status RETURNED."""
        position_id = position.get("id")
        if returned_position_ids and position_id and str(position_id) in returned_position_ids:
            return True

        rma = position.get("rma") or {}

        for case in rma.get("cases") or []:
            for rma_position in case.get("positions") or []:
                status = str(rma_position.get("status") or "").upper()
                if status == PATARules.RETURNED_STATUS:
                    return True

        return False

    @staticmethod
    def _is_position_rejected(position: dict[str, Any]) -> bool:
        return str(position.get("state") or "").upper() == PATARules.REJECTED_STATE

    @staticmethod
    def _is_position_returned_or_rejected(
        position: dict[str, Any],
        returned_position_ids: set[str] | None = None,
    ) -> bool:
        return PATARules._is_position_rejected(position) or PATARules._is_position_returned(
            position,
            returned_position_ids,
        )

    @staticmethod
    def _is_order_fully_returned(order_data: dict[str, Any]) -> bool:
        """Return True when every order position is returned or rejected."""
        positions = order_data.get("positions") or []
        returned_position_ids = PATARules._get_returned_position_ids(order_data)
        return bool(positions) and all(
            PATARules._is_position_returned_or_rejected(position, returned_position_ids)
            for position in positions
        )

    @staticmethod
    def _has_pending_positions(order_data: dict[str, Any]) -> bool:
        """Return True if any position is still created, active, or accepted."""
        return any(
            str(position.get("state") or "").upper() in PATARules.PENDING_STATES
            for position in order_data.get("positions") or []
        )

    @staticmethod
    def _position_selling_price(position: dict[str, Any]) -> int:
        """Return selling price in major currency units, defaulting to 0."""
        try:
            return int((position.get("sellingPrice") or 0) // 100)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _get_partial_return_amount(order_data: dict[str, Any]) -> int | None:
        """
        Return the total selling price for positions that were not returned/rejected.

        A partial return exists only when at least one position is returned/rejected
        and at least one position is still kept.
        """
        positions = order_data.get("positions") or []
        if not positions:
            return None

        returned_position_ids = PATARules._get_returned_position_ids(order_data)
        returned_or_rejected = [
            position
            for position in positions
            if PATARules._is_position_returned_or_rejected(position, returned_position_ids)
        ]
        kept_positions = [
            position
            for position in positions
            if not PATARules._is_position_returned_or_rejected(position, returned_position_ids)
        ]

        if returned_or_rejected and kept_positions:
            return sum(PATARules._position_selling_price(position) for position in kept_positions)

        return None

    @staticmethod
    def _is_fully_accepted_and_processed(order_data: dict[str, Any]) -> bool:
        """
        Return True when all positions are shipped and no RMA positions exist.
        """
        positions = order_data.get("positions") or []
        if not positions:
            return False

        if not all(str(position.get("state") or "").upper() == PATARules.SHIPPED_STATE for position in positions):
            return False

        rma = order_data.get("rma") or {}
        for case in rma.get("cases") or []:
            if case.get("positions"):
                return False

        return True

    @staticmethod
    def calculate_action_reason_and_amount(
        response: dict[str, Any],
    ) -> tuple[str | None, int | None]:
        """
        Determine PATA reason and action cost from a full order response.

        Returns:
            ("OTHER", 0): voucher, fraud, pending order, or no positions
            ("ITEM_RETURNED", 0): all positions returned/rejected
            ("ORDER_UPDATE", amount): some positions returned/rejected
            (None, None): fully accepted/processed or no matching rule
        """
        order_data = response.get("data") or {}

        if PATARules.detect_fraud(response):
            return "OTHER", 0

        if PATARules.has_voucher_code(order_data):
            return "OTHER", 0

        positions = order_data.get("positions") or []
        if not positions:
            return "OTHER", 0

        if PATARules._is_order_fully_returned(order_data):
            return "ITEM_RETURNED", 0

        partial_amount = PATARules._get_partial_return_amount(order_data)
        if partial_amount is not None:
            return "ORDER_UPDATE", partial_amount

        if PATARules._has_pending_positions(order_data):
            return "OTHER", 0

        if PATARules._is_fully_accepted_and_processed(order_data):
            return None, None

        return None, None

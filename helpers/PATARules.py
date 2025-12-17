from typing import Tuple, Optional

class PATARules:
    FRAUD_KEYWORDS = [
        "fraud risk",
        "fraud order",
        "do not refund",
        "do not issue refund",
        "declined rma process",
        "lost parcels process",
    ]
    @staticmethod
    def has_voucher_code(response: dict) -> bool:
        """
        Return True if voucher.code exists and is non-empty (after strip).
        """
        voucher = response.get("voucher") or {}
        code = voucher.get("code")
        return bool(code and str(code).strip())

    @staticmethod
    def detect_fraud(response: dict) -> bool:
        """
        Scan order history for fraud-related messages.
        Returns True if found.
        """
        data = response.get("data", {})
        history = data.get("history", [])
        if not history:
            return False

        for note in history:
            message = (note.get("message") or "").lower()
            note_type = (note.get("type") or "").lower()
            if note_type == "internal note":
                for keyword in PATARules.FRAUD_KEYWORDS:
                    if keyword in message:
                        print(f"⚠️ Fraud/Do-Not-Refund detected: '{message}'")
                        return True
                    else:print(f"⚠️ Fraud not detected: '{message}'")

        return False

    @staticmethod
    def calculate_action_reason_and_amount(response: dict) -> Tuple[Optional[str], Optional[int]]:
        """
        Determine PATA Reason and Action cost from a full order response.

        Returns:
            - ("OTHER", 0) when voucher present or any pending position
            - ("ITEM_RETURNED", 0) when ALL positions are returned/rejected
            - ("ORDER_UPDATE", action_cost) when SOME positions returned/rejected (partial)
            - (None, None) when order fully accepted/processed (no change needed)
        """
        # 1) Voucher check
        order_data = response.get("data", {})
        print(f"order data: {order_data}")


        if PATARules.detect_fraud(response):
            return "OTHER", 0

        if PATARules.has_voucher_code(order_data):
            return "OTHER", 0

        positions = order_data.get("positions") or []
        if not positions:
            return "OTHER", 0

        # 🔹 Debug: Print orderId and positions info
        order_id = order_data.get("orderId") or order_data.get("OrderId") or "<no id>"
        print(f"Order {str(order_id)} has {len(positions)} positions:")
        for i, p in enumerate(positions, start=1):
            amount = p.get("amount", "<no amount>")
            status = p.get("status", "<no status>")
            print(f"  Position {i}: amount={amount}, status={status}")



        def to_int(v):
            try:
                return int(v)
            except Exception:
                return 0

        def status_of(p):
            return (p.get("status") or "").strip().lower()


        def is_pending(p):
            return to_int(p.get("amount", 0)) >= 1 and status_of(p) == "pending"


        def is_returned_or_rejected(p):
            amt = to_int(p.get("amount", 0))
            st = status_of(p)
            # Pending in multi-position order treated as returned/rejected
            if is_pending(p) and len(positions) > 1:
                return True
            return (st == "rejected" and amt == 1) or (amt == 0 and st in ("accepted", "sent"))

        # 2) Pending positions -> OTHER
        if len(positions) == 1 and status_of(positions[0]) == "pending" and to_int(positions[0].get("amount", 0)) >= 1:
            return "OTHER", 0

        # 3) Fully returned
        if all(is_returned_or_rejected(p) for p in positions):
            print("All positions returned/rejected, returning ITEM_RETURNED")
            return "ITEM_RETURNED", 0

        # 4) Partial return
        if any(is_returned_or_rejected(p) for p in positions):
            total_unrefunded = sum(
                to_int((p.get("price") or {}).get("amount", 0))
                for p in positions if not is_returned_or_rejected(p)
            )
            action_cost = total_unrefunded // 100
            return "ORDER_UPDATE", action_cost

        # 5) Fully processed (all sent, amount=1)
        print("Order fully processed, returning None")
        return None, None

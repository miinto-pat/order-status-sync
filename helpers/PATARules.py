from typing import Tuple, Optional

class PATARules:
    @staticmethod
    def has_voucher_code(response: dict) -> bool:
        """
        Return True if voucher.code exists and is non-empty (after strip).
        """
        voucher = response.get("voucher") or {}
        code = voucher.get("code")
        return bool(code and str(code).strip())

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

        if PATARules.has_voucher_code(order_data):
            return "OTHER", 0

        positions = order_data.get("positions") or []
        if not positions:
            return "OTHER", 0

        # 🔹 Debug: Print orderId and positions info
        order_id = order_data.get("orderId") or order_data.get("OrderId") or "<no id>"
        # print(f"Order {str(order_id)} has {len(positions)} positions:")
        for i, p in enumerate(positions, start=1):
            amount = p.get("amount", "<no amount>")
            status = p.get("status", "<no status>")
            # print(f"  Position {i}: amount={amount}, status={status}")

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
            return (st == "rejected" and amt == 1) or (amt == 0 and st in ("accepted", "sent"))

        # 2) Pending positions -> OTHER
        if any(is_pending(p) for p in positions):
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
            print("Some positions returned/rejected, returning ORDER_UPDATE")
            return "ORDER_UPDATE", action_cost

        # 5) Fully processed (all sent, amount=1)
        print("Order fully processed, returning None")
        return None, None

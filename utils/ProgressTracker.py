from copy import deepcopy


ACTION_KEYS = ("OTHER", "ITEM_RETURNED", "ORDER_UPDATE", "Not_Modified", "Not_Processed", "NONE")


class ProgressTracker:
    def __init__(self, markets):
        self.markets_order = list(markets or [])
        self.current_market = None
        self.phase = "idle"
        self.message = "Idle"
        self.markets = {
            market: self._new_market_state(market)
            for market in self.markets_order
        }

    def start_run(self, message="Starting bot..."):
        self.phase = "starting"
        self.message = message

    def start_market(self, market, message=None):
        self.current_market = market
        self.phase = "market"
        state = self._state_for(market)
        state["status"] = "running"
        state["phase"] = "loading_actions"
        state["message"] = message or f"Loading actions for {market}..."
        self.message = state["message"]

    def actions_loaded(self, market, total_actions):
        state = self._state_for(market)
        state["status"] = "running"
        state["phase"] = "processing_actions"
        state["total_actions"] = max(0, int(total_actions or 0))
        state["remaining_actions"] = state["total_actions"]
        state["message"] = f"Processing {state['total_actions']} action(s) for {market}..."
        self.current_market = market
        self.phase = "actions"
        self.message = state["message"]

    def action_completed(self, market, processed_actions, stats=None):
        state = self._state_for(market)
        self._apply_stats(state, stats or {})
        state["processed_actions"] = max(0, int(processed_actions or 0))
        state["remaining_actions"] = max(0, state["total_actions"] - state["processed_actions"])
        state["status"] = "running"
        state["phase"] = "processing_actions"
        state["message"] = (
            f"{market}: processed {state['processed_actions']} of {state['total_actions']} action(s)."
        )
        self.current_market = market
        self.phase = "actions"
        self.message = state["message"]

    def finish_market(self, market, stats=None):
        state = self._state_for(market)
        self._apply_stats(state, stats or {})
        state["status"] = "finished"
        state["phase"] = "finished"
        state["processed_actions"] = state["total_actions"]
        state["remaining_actions"] = 0
        state["message"] = f"{market}: finished."
        self.current_market = None
        self.phase = "market_finished"
        self.message = state["message"]

    def fail_market(self, market, error):
        state = self._state_for(market)
        state["status"] = "error"
        state["phase"] = "error"
        state["error"] = str(error)
        state["remaining_actions"] = max(0, state["total_actions"] - state["processed_actions"])
        state["message"] = f"{market}: failed."
        self.current_market = None
        self.phase = "market_error"
        self.message = state["message"]

    def start_zip(self):
        self.phase = "creating_zip"
        self.message = "Creating ZIP with result files..."

    def finish_run(self, message="Bot finished."):
        self.phase = "finished"
        self.current_market = None
        self.message = message
        for state in self.markets.values():
            if state["status"] not in ("finished", "error"):
                state["status"] = "finished"
                state["phase"] = "finished"
                state["processed_actions"] = state["total_actions"]
                state["remaining_actions"] = 0

    def fail_run(self, message):
        self.phase = "error"
        self.current_market = None
        self.message = str(message)

    def snapshot(self):
        totals = {
            "total_actions": 0,
            "processed_actions": 0,
            "remaining_actions": 0,
            "successful_actions": 0,
            "skipped_actions": 0,
            "error_actions": 0,
        }
        completed_markets = 0
        progress_units = 0.0

        for state in self.markets.values():
            totals["total_actions"] += state["total_actions"]
            totals["processed_actions"] += state["processed_actions"]
            totals["remaining_actions"] += state["remaining_actions"]
            totals["successful_actions"] += state["successful_actions"]
            totals["skipped_actions"] += state["skipped_actions"]
            totals["error_actions"] += state["error_actions"]

            if state["status"] in ("finished", "error"):
                completed_markets += 1
                progress_units += 1
            elif state["status"] == "running" and state["total_actions"] > 0:
                progress_units += min(1, state["processed_actions"] / state["total_actions"])

        total_markets = len(self.markets_order)
        percent = 0 if total_markets == 0 else round((progress_units / total_markets) * 100, 1)

        return {
            "phase": self.phase,
            "message": self.message,
            "percent": min(100, percent),
            "total_markets": total_markets,
            "completed_markets": completed_markets,
            "current_market": self.current_market,
            "markets": deepcopy(self.markets),
            **totals,
        }

    def _state_for(self, market):
        if market not in self.markets:
            self.markets_order.append(market)
            self.markets[market] = self._new_market_state(market)
        return self.markets[market]

    def _new_market_state(self, market):
        return {
            "market": market,
            "status": "pending",
            "phase": "pending",
            "message": "",
            "total_actions": 0,
            "processed_actions": 0,
            "remaining_actions": 0,
            "successful_actions": 0,
            "skipped_actions": 0,
            "error_actions": 0,
            "error": "",
            **{key: 0 for key in ACTION_KEYS},
        }

    def _apply_stats(self, state, stats):
        for key in ACTION_KEYS:
            state[key] = int(stats.get(key) or 0)
        if stats.get("total_actions") is not None:
            state["total_actions"] = int(stats.get("total_actions") or 0)

        state["successful_actions"] = (
            state["OTHER"] + state["ITEM_RETURNED"] + state["ORDER_UPDATE"]
        )
        state["skipped_actions"] = state["Not_Modified"] + state["NONE"]
        state["error_actions"] = state["Not_Processed"]

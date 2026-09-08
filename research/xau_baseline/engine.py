def trade_r_long(*, ask_entry: float, bid_exit: float, stop: float) -> float:
    risk = ask_entry - stop
    if risk <= 0:
        raise ValueError("long risk must be positive")
    return (bid_exit - ask_entry) / risk


def trade_r_short(*, bid_entry: float, ask_exit: float, stop: float) -> float:
    risk = stop - bid_entry
    if risk <= 0:
        raise ValueError("short risk must be positive")
    return (bid_entry - ask_exit) / risk


def resolve_long_bar(*, bid_low: float, bid_high: float, stop: float, target: float):
    if bid_low <= stop:
        return -1.0
    if bid_high >= target:
        return None
    return None

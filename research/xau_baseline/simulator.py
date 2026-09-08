from backtest_core import resolve_bar_r


def summarize_rs(rs, risk_fraction=0.0036):
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    wins = 0
    for raw_r in rs:
        r = float(raw_r)
        if r > 0:
            wins += 1
            gross_profit += r
        elif r < 0:
            gross_loss += -r
        equity *= 1.0 + risk_fraction * r
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, 1.0 - equity / peak)
    n = len(rs)
    return {
        "trades": n,
        "wins": wins,
        "win_rate": wins / n if n else 0.0,
        "sum_r": sum(float(r) for r in rs),
        "expectancy_r": sum(float(r) for r in rs) / n if n else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
        "equity_multiple": equity,
        "growth_pct": (equity - 1.0) * 100.0,
        "max_dd_pct": max_dd * 100.0,
    }


def simulate_signals(df, long_signal, short_signal, long_stop, short_stop, *, rr, max_hold_bars=240, risk_fraction=0.0036):
    rs = []
    trades = []
    i = 0
    n = len(df)
    while i < n - 1:
        side = None
        if bool(long_signal.iloc[i]):
            side = "long"
        elif bool(short_signal.iloc[i]):
            side = "short"
        if side is None:
            i += 1
            continue

        entry_index = i + 1
        entry_row = df.iloc[entry_index]
        if side == "long":
            entry = float(entry_row["ask_open"])
            stop = float(long_stop.iloc[i])
            risk = entry - stop
            if risk <= 0:
                i += 1
                continue
            target = entry + float(rr) * risk
        else:
            entry = float(entry_row["bid_open"])
            stop = float(short_stop.iloc[i])
            risk = stop - entry
            if risk <= 0:
                i += 1
                continue
            target = entry - float(rr) * risk

        exit_index = None
        exit_reason = None
        trade_r = None
        exit_price = None
        last_index = min(n - 1, entry_index + int(max_hold_bars))
        for j in range(entry_index, last_index + 1):
            row = df.iloc[j]
            hit_r = resolve_bar_r(
                side,
                stop=stop,
                target=target,
                rr=rr,
                bid_low=float(row["bid_low"]),
                bid_high=float(row["bid_high"]),
                ask_low=float(row["ask_low"]),
                ask_high=float(row["ask_high"]),
            )
            if hit_r is not None:
                trade_r = float(hit_r)
                exit_index = j
                exit_reason = "stop" if hit_r < 0 else "target"
                exit_price = stop if hit_r < 0 else target
                break
            if j == last_index:
                exit_index = j
                exit_reason = "timeout" if j < n - 1 else "end"
                if side == "long":
                    exit_price = float(row["bid_close"])
                    trade_r = (exit_price - entry) / risk
                else:
                    exit_price = float(row["ask_close"])
                    trade_r = (entry - exit_price) / risk
                break

        if trade_r is not None:
            rs.append(trade_r)
            trades.append({
                "side": side,
                "signal_index": i,
                "entry_index": entry_index,
                "exit_index": exit_index,
                "entry_price": entry,
                "stop": stop,
                "target": target,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "r": trade_r,
                "hold_bars": exit_index - entry_index,
            })
            i = int(exit_index) + 1
        else:
            i += 1

    return summarize_rs(rs, risk_fraction=risk_fraction), trades

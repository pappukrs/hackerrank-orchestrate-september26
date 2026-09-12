from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .reconstruct import Flow

EPS = 1e-6


def _daily_net(flows: list[Flow], stops: set[str], reduces: dict[str, float]) -> dict[date, float]:
    net: dict[date, float] = defaultdict(float)
    for f in flows:
        if f.event_id and f.event_id in stops:
            continue
        amt = f.amount
        if f.amount < 0 and f.event_id and f.event_id in reduces:
            amt = -reduces[f.event_id]
        net[f.day] += amt
    return net


def curve(start_balance: float, flows: list[Flow], start: date, end: date,
          payments: list[tuple[date, float]] | None = None,
          stops: set[str] | None = None,
          reduces: dict[str, float] | None = None) -> list[tuple[date, float]]:
    """Running end-of-day balance at each dated change, including the start point."""
    net = _daily_net(flows, stops or set(), reduces or {})
    for d, a in (payments or []):
        net[d] += -a
    days = sorted(d for d in net if start <= d <= end)
    running = start_balance
    series = [(start, running)]
    for d in days:
        running += net[d]
        if d == start:
            series[0] = (start, running)
        else:
            series.append((d, running))
    return series


def min_balance(series: list[tuple[date, float]]) -> float:
    return min(b for _, b in series)


def baseline_min(start_balance, flows, start, end) -> float:
    return min_balance(curve(start_balance, flows, start, end))


def amount_safe_to_pay(start_balance, flows, start, end, min_keep, requested) -> float:
    bmin = baseline_min(start_balance, flows, start, end)
    safe = bmin - min_keep
    return max(0.0, min(requested, safe))


def earliest_full_date(start_balance, flows, start, end, min_keep, requested) -> date | None:
    """Earliest day D such that paying the full `requested` as one payment on D keeps the
    balance >= min_keep for the rest of the window."""
    series = curve(start_balance, flows, start, end)
    threshold = min_keep + requested - EPS
    # candidate days = start + each event day; find earliest with suffix-min >= threshold
    n = len(series)
    suffix = [0.0] * n
    run = float("inf")
    for i in range(n - 1, -1, -1):
        run = min(run, series[i][1])
        suffix[i] = run
    for i in range(n):
        if suffix[i] >= threshold:
            return series[i][0]
    return None


def forecast_min_with_plan(start_balance, flows, start, end,
                           payments, stops=None, reduces=None) -> float:
    return min_balance(curve(start_balance, flows, start, end,
                             payments=payments, stops=stops, reduces=reduces))

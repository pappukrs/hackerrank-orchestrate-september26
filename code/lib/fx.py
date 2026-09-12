from __future__ import annotations

import bisect
from datetime import date

from .models import ExchangeRate


class RateTable:
    """Dated FX lookup. Rates are fixed monthly points; for a given date we use
    the latest rate on or before it (falling back to the earliest if the date
    predates all rates). Direct pairs are used when present, otherwise the
    inverse rate is applied."""

    def __init__(self, rates: list[ExchangeRate]):
        self._by_pair: dict[tuple[str, str], list[tuple[date, float]]] = {}
        for r in rates:
            self._by_pair.setdefault((r.from_currency, r.to_currency), []).append(
                (r.rate_date, r.rate)
            )
        for pair in self._by_pair:
            self._by_pair[pair].sort(key=lambda t: t[0])

    def _lookup(self, frm: str, to: str, on: date) -> float | None:
        series = self._by_pair.get((frm, to))
        if not series:
            return None
        dates = [d for d, _ in series]
        i = bisect.bisect_right(dates, on) - 1
        if i < 0:
            i = 0
        return series[i][1]

    def rate(self, frm: str, to: str, on: date) -> float:
        if frm == to:
            return 1.0
        direct = self._lookup(frm, to, on)
        if direct is not None:
            return direct
        inv = self._lookup(to, frm, on)
        if inv:
            return 1.0 / inv
        raise KeyError(f"no exchange rate for {frm}->{to} on {on}")

    def convert(self, amount: float, frm: str, to: str, on: date) -> float:
        if amount is None:
            return 0.0
        if not frm or frm == to:
            return amount
        return amount * self.rate(frm, to, on)

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .fx import RateTable
from .loaders import Dataset
from .messages import classify
from .models import Event, Profile, Request

FORECAST_DAYS = 90

# categories whose spend recurs many times per month (variable amount)
FREQUENT = {"groceries", "transport", "dining", "shopping", "entertainment"}


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


@dataclass
class Flow:
    day: date
    amount: float          # signed home-currency: + inflow, - outflow
    category: str
    flexibility: str
    event_id: str | None
    kind: str              # 'recurring' | 'scheduled' | 'salary'
    min_allowed: float | None = None   # home-currency floor for reducible series


class Reconstructor:
    def __init__(self, ds: Dataset, rt: RateTable):
        self.ds = ds
        self.rt = rt

    def _home(self, amount, currency, home, on):
        return self.rt.convert(amount or 0.0, currency, home, on)

    def _salary_effects(self, uid: str):
        eff = []
        for m in self.ds.messages_by_user.get(uid, []):
            e = classify(m)
            if e.kind.startswith("salary") or e.kind == "income_end":
                eff.append(e)
        return eff

    def build_flows(self, req: Request) -> list[Flow]:
        uid = req.user_id
        p = self.ds.profiles_by_user[uid]
        home = p.home_currency
        start = req.request_date
        end = start + timedelta(days=FORECAST_DAYS)
        evs = self.ds.events_by_user.get(uid, [])

        flows: list[Flow] = []
        covered: set[tuple[str, date]] = set()

        # 1) future scheduled/pending DEBITS = reserved outflows (bills)
        for e in evs:
            sd = e.settlement_date or e.event_date
            if sd is None or sd < start or sd > end:
                continue
            if e.status in ("scheduled", "pending") and e.direction == "debit":
                amt = self._home(e.amount, e.currency, home, sd)
                flows.append(Flow(sd, -amt, e.category, e.flexibility, e.event_id, "scheduled"))
                covered.add((e.category, sd))

        # 2) recurring EXPENSES projected from settled history
        flows += self._project_expenses(uid, home, start, end, covered)

        # 3) SALARY projected + message amendments
        flows += self._project_salary(uid, home, start, end)

        return flows

    def _settled_hist(self, evs, direction, start):
        cutoff = start - timedelta(days=200)
        return [e for e in evs
                if e.direction == direction and e.status == "settled"
                and e.settlement_date and cutoff <= e.settlement_date < start]

    def _project_expenses(self, uid, home, start, end, covered) -> list[Flow]:
        evs = self.ds.events_by_user.get(uid, [])
        hist = self._settled_hist(evs, "debit", start)
        by_cat: dict[str, list[Event]] = defaultdict(list)
        for e in hist:
            if e.category == "salary":
                continue
            by_cat[e.category].append(e)

        out: list[Flow] = []
        for cat, lst in by_cat.items():
            lst.sort(key=lambda e: e.settlement_date)
            if len(lst) < 2:
                continue
            gaps = [(lst[i].settlement_date - lst[i - 1].settlement_date).days
                    for i in range(1, len(lst))]
            med_gap = statistics.median(gaps)
            last = lst[-1]
            flex = last.flexibility
            rep_id = last.event_id if flex != "fixed" else None
            min_home = (self._home(last.minimum_allowed_amount, last.currency, home, last.settlement_date)
                        if last.minimum_allowed_amount is not None else None)

            if cat in FREQUENT or med_gap < 24:
                recent = lst[-6:]
                amt = statistics.mean(self._home(e.amount, e.currency, home, e.settlement_date)
                                      for e in recent)
                step = max(int(round(med_gap)), 1)
                d = last.settlement_date + timedelta(days=step)
                while d <= end:
                    if d >= start:
                        out.append(Flow(d, -amt, cat, flex, rep_id, "recurring", min_home))
                    d = d + timedelta(days=step)
            else:
                recent = lst[-3:]
                amt = statistics.mean(self._home(e.amount, e.currency, home, e.settlement_date)
                                      for e in recent)
                d = add_months(last.settlement_date, 1)
                while d <= end:
                    if d >= start and not self._near_covered(covered, cat, d):
                        out.append(Flow(d, -amt, cat, flex, rep_id, "recurring", min_home))
                    d = add_months(d, 1)
        return out

    def _near_covered(self, covered, cat, d) -> bool:
        return any(c == cat and abs((cd - d).days) <= 6 for (c, cd) in covered)

    def _project_salary(self, uid, home, start, end) -> list[Flow]:
        evs = self.ds.events_by_user.get(uid, [])
        sal_settled = sorted(
            [e for e in evs if e.category == "salary" and e.direction == "credit"
             and e.status == "settled" and e.settlement_date and e.settlement_date < start],
            key=lambda e: e.settlement_date)
        sal_future = sorted(
            [e for e in evs if e.category == "salary" and e.direction == "credit"
             and e.status in ("scheduled", "pending") and e.settlement_date
             and start <= e.settlement_date <= end],
            key=lambda e: e.settlement_date)

        effects = self._salary_effects(uid)
        ended = any(e.kind == "income_end" for e in effects)
        first = next((e for e in effects if e.kind == "salary_first"), None)
        from_eff = next((e for e in effects if e.kind == "salary_from"), None)
        next_eff = next((e for e in effects if e.kind == "salary_next"), None)
        shift_eff = next((e for e in effects if e.kind == "salary_date_shift"), None)
        confirm_eff = next((e for e in effects if e.kind == "salary_confirm" and e.amount), None)

        occ: list[tuple[date, float]] = []   # (date, amount home)

        if sal_future:
            for e in sal_future:
                occ.append((e.settlement_date, self._home(e.amount, e.currency, home, e.settlement_date)))
            reg = occ[-1][1]
            last_date = sal_future[-1].settlement_date
        elif sal_settled:
            reg = statistics.median(self._home(e.amount, e.currency, home, e.settlement_date)
                                    for e in sal_settled[-3:])
            last_date = sal_settled[-1].settlement_date
        elif first and first.on_date:
            reg = self._home(first.amount, first.currency, home, first.on_date)
            last_date = add_months(first.on_date, -1)
        else:
            return []

        if confirm_eff:
            reg = self._home(confirm_eff.amount, confirm_eff.currency, home, start)

        # first salary from a brand-new employer overrides the whole forward series
        if first and first.on_date and not sal_future:
            occ = []
            reg = self._home(first.amount, first.currency, home, first.on_date)
            last_date = add_months(first.on_date, -1)

        d = add_months(last_date, 1)
        while d <= end:
            if d >= start:
                occ.append((d, reg))
            d = add_months(d, 1)

        # apply amendments to the projected (non-anchored) occurrences
        out: list[Flow] = []
        occ.sort(key=lambda t: t[0])
        for i, (dd, amt) in enumerate(occ):
            if from_eff and from_eff.on_date and dd >= from_eff.on_date:
                amt = self._home(from_eff.amount, from_eff.currency, home, dd)
            if next_eff and i == 0 and not sal_future:
                amt = self._home(next_eff.amount, next_eff.currency, home, dd)
            if shift_eff and i == 0 and shift_eff.on_date and start <= shift_eff.on_date <= end:
                dd = shift_eff.on_date
            if not ended:
                out.append(Flow(dd, +amt, "salary", "fixed", None, "salary"))
        return out

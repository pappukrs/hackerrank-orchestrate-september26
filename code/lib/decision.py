from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .forecast import (EPS, amount_safe_to_pay, baseline_min, curve,
                       earliest_full_date, forecast_min_with_plan, min_balance)
from .fx import RateTable
from .loaders import Dataset
from .models import PaymentOption, Request
from .reconstruct import FORECAST_DAYS, Flow, Reconstructor

OUT_COLUMNS = [
    "request_id", "amount_safe_to_pay", "affordability_status",
    "recommended_payment_method", "payment_plan", "earliest_date_for_full_payment",
    "spending_changes_needed", "decision_explanation",
]


def _num(x: float) -> str:
    x = round(float(x) + 0.0, 2)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _money(cur: str, x: float) -> str:
    x = round(float(x), 2)
    if abs(x - round(x)) < 1e-9:
        return f"{cur} {int(round(x)):,}"
    return f"{cur} {x:,.2f}"


@dataclass
class Change:
    kind: str        # 'stop' | 'reduce'
    event_id: str
    amount: float | None = None   # home-currency reduce target
    savings: float = 0.0

    def token(self) -> str:
        if self.kind == "stop":
            return f"stop:{self.event_id}"
        return f"reduce_to:{self.event_id}:{_num(self.amount)}"


@dataclass
class Plan:
    method: str
    payments: list[tuple[date, float]]
    total_paid: float
    changes: list[Change]
    n_payments: int
    completes: bool
    option_id: str | None
    start: date


@dataclass
class Decision:
    request_id: str
    amount_safe_to_pay: float
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str

    def row(self) -> dict:
        return {
            "request_id": self.request_id,
            "amount_safe_to_pay": _num(self.amount_safe_to_pay),
            "affordability_status": self.affordability_status,
            "recommended_payment_method": self.recommended_payment_method,
            "payment_plan": self.payment_plan,
            "earliest_date_for_full_payment": self.earliest_date_for_full_payment,
            "spending_changes_needed": self.spending_changes_needed,
            "decision_explanation": self.decision_explanation,
        }


class Engine:
    def __init__(self, ds: Dataset, rt: RateTable):
        self.ds = ds
        self.rt = rt
        self.rc = Reconstructor(ds, rt)

    def _candidate_changes(self, flows: list[Flow], profile) -> list[Change]:
        seen: dict[str, dict] = {}
        for f in flows:
            if f.amount >= 0 or not f.event_id or f.kind != "recurring":
                continue
            info = seen.setdefault(f.event_id, {
                "cat": f.category, "flex": f.flexibility,
                "per_occ": -f.amount, "count": 0, "min": f.min_allowed})
            info["count"] += 1
        out: list[Change] = []
        for eid, i in seen.items():
            can_stop = i["flex"] in ("stoppable", "reducible_or_stoppable") and i["cat"] in profile.willing_to_stop
            can_reduce = (i["flex"] in ("reducible", "reducible_or_stoppable")
                          and i["cat"] in profile.willing_to_reduce and i["min"] is not None
                          and i["per_occ"] > i["min"])
            best = None
            if can_stop:
                best = Change("stop", eid, None, i["per_occ"] * i["count"])
            if can_reduce:
                red = Change("reduce", eid, i["min"], (i["per_occ"] - i["min"]) * i["count"])
                if best is None or red.savings > best.savings:
                    best = red
            if best:
                out.append(best)
        out.sort(key=lambda c: -c.savings)
        return out

    def _pick_changes(self, flows, profile, needed) -> list[Change] | None:
        cands = self._candidate_changes(flows, profile)
        chosen: list[Change] = []
        total = 0.0
        for c in cands:
            if total >= needed - EPS:
                break
            chosen.append(c)
            total += c.savings
            if len(chosen) >= 3:
                break
        if total >= needed - EPS:
            return chosen
        return None

    def decide(self, req: Request) -> Decision:
        p = self.ds.profiles_by_user[req.user_id]
        home = p.home_currency
        bal, mn = p.current_available_balance, p.minimum_balance_to_keep
        start = req.request_date
        end = start + timedelta(days=FORECAST_DAYS)
        requested = req.requested_amount
        deadline = req.desired_completion_date or end
        methods = set(p.payment_methods)
        flows = self.rc.build_flows(req)

        bmin = baseline_min(bal, flows, start, end)
        safe = max(0.0, min(requested, bmin - mn))
        efd = earliest_full_date(bal, flows, start, end, mn, requested)

        options = self.ds.options_by_request.get(req.request_id, [])
        plans: list[Plan] = []

        # A) full payment today
        if "full_payment" in methods and bmin - mn >= requested - EPS:
            plans.append(Plan("full_payment", [(start, requested)], requested, [], 1, True, None, start))

        # B) installments (must match a supplied option)
        if "installments" in methods:
            for opt in options:
                if opt.payment_method != "installments":
                    continue
                if p.max_installment_months is not None and opt.number_of_payments > p.max_installment_months:
                    continue
                sched = opt.schedule()
                if not sched:
                    continue
                pays = [(d, opt.payment_amount) for d in sched]
                in_window = [(d, a) for d, a in pays if start <= d <= end]
                m = forecast_min_with_plan(bal, flows, start, end, in_window)
                completes = sched[-1] <= deadline
                if m >= mn - EPS:
                    plans.append(Plan("installments", pays, opt.total_payable_amount,
                                      [], opt.number_of_payments, completes, opt.payment_option_id, sched[0]))

        # C) partial payment
        if ("partial_payment" in methods and req.allows_partial_payment
                and 0 < safe < requested and efd and efd <= deadline):
            pays = [(start, safe), (efd, requested - safe)]
            m = forecast_min_with_plan(bal, flows, start, end, pays)
            if m >= mn - EPS:
                plans.append(Plan("partial_payment", pays, requested, [], 2, True, None, start))

        # D) full payment today enabled by spending changes
        if "full_payment" in methods and bmin - mn < requested - EPS:
            needed = requested - (bmin - mn)
            changes = self._pick_changes(flows, p, needed)
            if changes:
                stops = {c.event_id for c in changes if c.kind == "stop"}
                reduces = {c.event_id: c.amount for c in changes if c.kind == "reduce"}
                m = forecast_min_with_plan(bal, flows, start, end, [(start, requested)], stops, reduces)
                if m >= mn - EPS:
                    plans.append(Plan("full_payment", [(start, requested)], requested,
                                      changes, 1, True, None, start))

        # E) wait — full payment becomes safe later
        if "full_payment" in methods and efd and efd > start and efd <= end:
            plans.append(Plan("wait", [(efd, requested)], requested, [], 1, efd <= deadline, None, efd))

        safe_plans = [pl for pl in plans if True]
        if not safe_plans:
            return self._not_affordable(req, p, safe, efd, deadline, end)

        safe_plans.sort(key=lambda pl: (
            0 if pl.completes else 1,
            1 if pl.changes else 0,
            pl.total_paid,
            pl.start.toordinal(),
            pl.n_payments,
            int(pl.option_id.split("_")[-1]) if pl.option_id else 0,
        ))
        best = safe_plans[0]
        return self._assemble(req, p, best, safe, efd, flows, start, end)

    def _plan_str(self, payments: list[tuple[date, float]]) -> str:
        return "|".join(f"{d.isoformat()}:{_num(a)}" for d, a in payments)

    def _post_low(self, req, p, best, flows, start, end) -> float:
        stops = {c.event_id for c in best.changes if c.kind == "stop"}
        reduces = {c.event_id: c.amount for c in best.changes if c.kind == "reduce"}
        pays = [(d, a) for d, a in best.payments if start <= d <= end]
        return forecast_min_with_plan(p.current_available_balance, flows, start, end, pays, stops, reduces)

    def _change_phrase(self, best: Change_list) -> str:  # type: ignore
        parts = []
        for c in best:
            if c.kind == "stop":
                parts.append(f"stop {self._desc(c.event_id)}")
            else:
                parts.append(f"reduce {self._desc(c.event_id)} to {_num(c.amount)}")
        return ", ".join(parts)

    def _desc(self, eid: str) -> str:
        e = self.ds.events_by_id.get(eid)
        return (e.description.lower() if e else eid)

    def _assemble(self, req, p, best: Plan, safe, efd, flows, start, end) -> Decision:
        home = p.home_currency
        mn = p.minimum_balance_to_keep
        low = self._post_low(req, p, best, flows, start, end)
        changes_str = "|".join(c.token() for c in best.changes) if best.changes else "none"
        efd_str = efd.isoformat() if efd else ""

        if best.method == "full_payment" and not best.changes:
            status = "affordable_now"
            expl = f"Pay {_money(home, req.requested_amount)} today. This leaves at least {_money(home, max(low, mn))} available over the next 90 days."
        elif best.method == "full_payment" and best.changes:
            status = "affordable_with_plan"
            expl = (f"{self._change_phrase(best.changes).capitalize()}, then pay {_money(home, req.requested_amount)} today. "
                    f"This leaves at least {_money(home, max(low, mn))} available.")
        elif best.method == "installments":
            status = "affordable_with_plan"
            per = best.payments[0][1]
            expl = (f"Use {best.n_payments} installments of {_money(home, per)}, starting "
                    f"{best.start.isoformat()}. This leaves at least {_money(home, max(low, mn))} available.")
        elif best.method == "partial_payment":
            status = "affordable_with_plan"
            rem = req.requested_amount - safe
            expl = (f"Pay {_money(home, safe)} today and the remaining {_money(home, rem)} on "
                    f"{efd_str}. This completes the full request and keeps the {_money(home, mn)} minimum protected.")
        elif best.method == "wait":
            status = "affordable_later"
            expl = (f"Pay {_money(home, req.requested_amount)} in full on {best.start.isoformat()}. "
                    f"Paying earlier would take the balance below the {_money(home, mn)} minimum.")
        else:
            status = "affordable_with_plan"
            expl = ""

        return Decision(
            request_id=req.request_id,
            amount_safe_to_pay=safe if best.method != "full_payment" or best.changes else req.requested_amount,
            affordability_status=status,
            recommended_payment_method=best.method,
            payment_plan=self._plan_str(best.payments),
            earliest_date_for_full_payment=efd_str,
            spending_changes_needed=changes_str,
            decision_explanation=expl,
        )

    def _not_affordable(self, req, p, safe, efd, deadline, end) -> Decision:
        home = p.home_currency
        mn = p.minimum_balance_to_keep
        if efd is None:
            expl = (f"Do not proceed with the {_money(home, req.requested_amount)} request. "
                    f"Although {_money(home, safe)} is available today, the full amount cannot be "
                    f"completed safely within 90 days.")
        else:
            expl = (f"Do not make this payment by {deadline.isoformat()}. None of the available options "
                    f"keeps the {_money(home, mn)} minimum protected.")
        return Decision(
            request_id=req.request_id,
            amount_safe_to_pay=safe,
            affordability_status="not_affordable",
            recommended_payment_method="not_recommended",
            payment_plan="none",
            earliest_date_for_full_payment=efd.isoformat() if efd else "",
            spending_changes_needed="none",
            decision_explanation=expl,
        )


# alias used only for the type hint above
Change_list = list

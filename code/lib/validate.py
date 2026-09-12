from __future__ import annotations

from datetime import date

from .decision import OUT_COLUMNS
from .loaders import Dataset
from .models import parse_date, parse_float

STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}


def _parse_plan(s: str) -> list[tuple[date, float]]:
    if s == "none" or not s:
        return []
    out = []
    for part in s.split("|"):
        d, a = part.split(":")
        out.append((parse_date(d), float(a)))
    return out


def validate(rows: list[dict], ds: Dataset) -> list[str]:
    errs: list[str] = []
    req_ids = [r.request_id for r in ds.requests]
    seen = [r["request_id"] for r in rows]

    if seen != req_ids:
        errs.append(f"row set/order mismatch: {len(seen)} rows vs {len(req_ids)} requests")

    for r in rows:
        rid = r["request_id"]
        req = ds.requests_by_id.get(rid)
        if not req:
            errs.append(f"{rid}: unknown request_id")
            continue
        if list(r.keys()) != OUT_COLUMNS:
            errs.append(f"{rid}: column order wrong")

        safe = parse_float(r["amount_safe_to_pay"])
        if safe is None or safe < -1e-6 or safe > req.requested_amount + 1e-6:
            errs.append(f"{rid}: amount_safe_to_pay {safe} out of [0, {req.requested_amount}]")

        st = r["affordability_status"]
        me = r["recommended_payment_method"]
        if st not in STATUSES:
            errs.append(f"{rid}: bad status {st}")
        if me not in METHODS:
            errs.append(f"{rid}: bad method {me}")

        plan = _parse_plan(r["payment_plan"])
        dates = [d for d, _ in plan]
        if dates != sorted(dates):
            errs.append(f"{rid}: payment_plan not chronological")

        efd = r["earliest_date_for_full_payment"]
        if st == "affordable_now":
            if efd != req.request_date.isoformat():
                errs.append(f"{rid}: affordable_now earliest must equal request_date")
            if me != "full_payment":
                errs.append(f"{rid}: affordable_now method must be full_payment")

        if me == "partial_payment":
            if st != "affordable_with_plan":
                errs.append(f"{rid}: partial_payment must be affordable_with_plan")
            if len(plan) != 2:
                errs.append(f"{rid}: partial_payment must have exactly 2 payments")
            elif abs(sum(a for _, a in plan) - req.requested_amount) > 1.0:
                errs.append(f"{rid}: partial payments must sum to requested_amount")

        if me == "installments":
            opts = ds.options_by_request.get(rid, [])
            match = False
            for o in opts:
                sched = o.schedule()
                if (o.payment_method == "installments" and len(sched) == len(plan)
                        and all(abs(a - o.payment_amount) < 0.01 for _, a in plan)
                        and [d for d, _ in plan] == sched):
                    match = True
                    break
            if not match:
                errs.append(f"{rid}: installments plan matches no supplied option")

        changes = r["spending_changes_needed"]
        if changes != "none":
            toks = changes.split("|")
            if len(toks) > 3:
                errs.append(f"{rid}: more than 3 spending changes")
            stops, reduces = set(), set()
            for t in toks:
                parts = t.split(":")
                eid = parts[1]
                ev = ds.events_by_id.get(eid)
                if not ev:
                    errs.append(f"{rid}: spending change references unknown {eid}")
                    continue
                if ev.flexibility == "fixed":
                    errs.append(f"{rid}: spending change targets non-flexible {eid}")
                if parts[0] == "stop":
                    stops.add(eid)
                elif parts[0] == "reduce_to":
                    reduces.add(eid)
            if stops & reduces:
                errs.append(f"{rid}: same event both stopped and reduced")

    return errs

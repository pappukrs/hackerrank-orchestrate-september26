import csv
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))
from lib.forecast import amount_safe_to_pay, baseline_min, earliest_full_date
from lib.fx import RateTable
from lib.loaders import DATASET_DIR, load_dataset
from lib.models import Request, parse_date, parse_float
from lib.reconstruct import FORECAST_DAYS, Reconstructor

ds = load_dataset()
rt = RateTable(ds.rates)
rc = Reconstructor(ds, rt)

with open(os.path.join(DATASET_DIR, "sample_requests.csv"), encoding="utf-8-sig") as fh:
    samples = list(csv.DictReader(fh))

print(f"{'req':10} {'gold_safe':>15} {'pred_safe':>15} {'err%':>7}  {'gold_status':20} {'g_early':11} {'p_early':11}")
tot_err = 0.0
n = 0
close = 0
for s in samples:
    req = Request.from_row(s)
    p = ds.profiles_by_user[req.user_id]
    bal, mn = p.current_available_balance, p.minimum_balance_to_keep
    start = req.request_date
    end = start + timedelta(days=FORECAST_DAYS)
    flows = rc.build_flows(req)

    pred_safe = amount_safe_to_pay(bal, flows, start, end, mn, req.requested_amount)
    pred_early = earliest_full_date(bal, flows, start, end, mn, req.requested_amount)
    gold_safe = parse_float(s["amount_safe_to_pay"]) or 0.0
    gold_status = s["affordability_status"]
    gold_early = s["earliest_date_for_full_payment"]

    denom = max(abs(gold_safe), 1.0)
    err = abs(pred_safe - gold_safe) / denom * 100
    tot_err += err
    n += 1
    if err <= 2:
        close += 1
    print(f"{req.request_id:10} {gold_safe:>15.2f} {pred_safe:>15.2f} {err:>6.1f}%  {gold_status:20} {gold_early:11} {str(pred_early):11}")

print(f"\nmean abs err%: {tot_err/n:.1f}   within2%: {close}/{n}")

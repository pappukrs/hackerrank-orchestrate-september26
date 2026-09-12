"""Self-evaluation: run the engine on the 25 public solved samples and report
affordability_status and recommended_payment_method accuracy."""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)

from lib.decision import Engine
from lib.fx import RateTable
from lib.loaders import DATASET_DIR, load_dataset
from lib.models import Request


def main() -> None:
    ds = load_dataset()
    engine = Engine(ds, RateTable(ds.rates))
    with open(os.path.join(DATASET_DIR, "sample_requests.csv"), encoding="utf-8-sig") as fh:
        samples = list(csv.DictReader(fh))

    ok_status = ok_method = 0
    for row in samples:
        d = engine.decide(Request.from_row(row))
        s = d.affordability_status == row["affordability_status"]
        m = d.recommended_payment_method == row["recommended_payment_method"]
        ok_status += s
        ok_method += m
        flag = "" if (s and m) else "   <-- mismatch"
        print(f"{row['request_id']:11} status {d.affordability_status:20} "
              f"method {d.recommended_payment_method:16}{flag}")

    n = len(samples)
    print(f"\naffordability_status: {ok_status}/{n}   recommended_payment_method: {ok_method}/{n}")


if __name__ == "__main__":
    main()

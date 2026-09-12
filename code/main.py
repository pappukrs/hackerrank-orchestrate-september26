"""Buy or Wait? — deterministic affordability engine entry point.

Reads dataset/ and writes output.csv (repo root) with one prediction per request.
Runs fully offline and deterministically; image evidence is pre-extracted into
code/evidence/image_amounts.json (see evaluation/usage_report.md).
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.decision import OUT_COLUMNS, Engine
from lib.fx import RateTable
from lib.loaders import REPO_ROOT, load_dataset
from lib.validate import validate


def main() -> None:
    ds = load_dataset()
    rt = RateTable(ds.rates)
    engine = Engine(ds, rt)

    rows = [engine.decide(req).row() for req in ds.requests]

    out_path = os.path.join(REPO_ROOT, "output.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    errs = validate(rows, ds)
    print(f"wrote {len(rows)} predictions -> {out_path}")
    if errs:
        print(f"VALIDATION: {len(errs)} issue(s):")
        for e in errs[:40]:
            print("  -", e)
    else:
        print("VALIDATION: all checks passed")


if __name__ == "__main__":
    main()

# Buy or Wait? — Solution

A deterministic AI financial agent that decides, for each request in
`dataset/requests.csv`, whether the user can safely afford a requested expense and how to pay
for it. Produces `output.csv` at the repository root.

## Run

```bash
python3 code/main.py
```

Requires Python 3.10+ and the standard library only (no third-party packages, no network, no
API keys). Writes `output.csv` (250 rows + header) to the repo root and runs a structural
validator over it.

Self-score against the 25 public solved examples:

```bash
python3 code/score_samples.py        # amount / date accuracy
python3 code/evaluation/main.py      # status + method accuracy
```

## Approach

The task is ~90% a deterministic 90-day cash-flow forecast and ~10% evidence extraction.

1. **Load** all `dataset/` CSVs into typed models (`lib/loaders.py`, `lib/models.py`).
2. **Evidence.** The 16 events with a blank `amount` are linked to images; their values were
   extracted once by a vision model and cached in `evidence/image_amounts.json`
   (`lib/evidence.py`). Messages are parsed deterministically, EN + Indonesian, into payroll
   / rent amendments (`lib/messages.py`). No model calls at run time.
3. **Reconstruct** each user's forward cash flows over 90 days (`lib/reconstruct.py`):
   scheduled/pending bills are reserved; recurring expenses are projected from settled
   history (monthly by day-of-month; frequent essentials at their cadence); salary is the
   modal monthly cluster (isolated from one-off extras, gig income rejected), anchored to any
   scheduled/pending salary event and adjusted by messages. FX via dated rates (`lib/fx.py`).
4. **Forecast + solve** (`lib/forecast.py`): a daily-net balance curve gives
   `amount_safe_to_pay = clamp(baseline_min - min_balance, 0, requested)` and the earliest
   date the full amount stays safe.
5. **Decide** (`lib/decision.py`): enumerate eligible plans (full / installments matching a
   supplied option / partial / spending-change-full / wait), verify each against the safety
   check, rank by the challenge's 6-tier rule, derive the status, and write a grounded
   explanation.
6. **Validate** (`lib/validate.py`): bounds, columns, plan chronology, installment-option
   match, partial two-payment sum, flexible-only spending changes, `affordable_now`
   invariants.

See `docs/PROJECT_MEMORY.md` for the full design notes and `evaluation/usage_report.md` for
the token/cost accounting.

## Layout

```
code/
  main.py                 entry point -> output.csv
  score_samples.py        self-score (amounts/dates) vs sample_requests.csv
  evidence/image_amounts.json   cached image extractions (16 events)
  evaluation/
    main.py               self-score (status/method) vs sample_requests.csv
    usage_report.md       token & cost analysis (required artifact)
  lib/                    loaders, models, fx, evidence, messages,
                          reconstruct, forecast, decision, validate
```

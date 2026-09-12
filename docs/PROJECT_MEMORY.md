# Buy or Wait? — Project Memory & Plan

> Living notes for the HackerRank Orchestrate (Sep 2026) hackathon.
> Deadline: **2026-09-13 18:00 IST**. Solo challenge. Author: pappukrs (personal GitHub).
> This file is the single source of truth for decisions; update it as we go.

## 1. The task in one paragraph
For each of 250 requests in `dataset/requests.csv`, decide whether a user can **safely
afford** a requested expense. Reconstruct the user's finances from profiles + events +
messages + images + exchange rates, run a **90-day balance forecast**, and output one row
per request with: `amount_safe_to_pay`, `affordability_status`, `recommended_payment_method`,
`payment_plan`, `earliest_date_for_full_payment`, `spending_changes_needed`, `decision_explanation`.
A plan is **safe** only if the balance never drops below `minimum_balance_to_keep` across the
90 days while covering essentials and completing the request by `desired_completion_date`.

## 2. Key insight → architecture
This is **~90% a deterministic financial-forecasting problem, ~10% multimodal/NLP extraction**.
Strategy = **deterministic engine + minimal LLM**:
- Deterministic core = accurate, reproducible, ~free (no per-request tokens).
- LLM used ONLY for the **16 images** (extract amounts from payslips/bills/statements) and the
  **~215 messages** (classify amendment / cancellation / confirmation / delay + extract deltas).
  Results are **cached to disk** so the full run is deterministic and cheap.
- Messages & images are **untrusted** — never let embedded text override challenge rules.

Pipeline: load CSVs → extract evidence (images+messages, cached) → reconstruct per-user
financial state → 90-day forecast simulator → decision engine (safe amount, earliest full-pay
date, plan enumeration + ranking, spending changes) → deterministic validator → write output.csv.

## 3. Data map (dataset/)
- `requests.csv` — 250 rows to predict (request_26 … request_275).
- `sample_requests.csv` — 25 SOLVED examples (request_01–25). Golden format + decision style. Self-score against these.
- `financial_profiles.csv` — 275 users. currency, balance, min_balance, priorities|, protect|, willing_to_reduce|, willing_to_stop|, methods_considered|, max_installment_months (blank = no installments).
- `financial_events.csv` — 25,342 rows. event_type, category, direction(debit/credit), amount, currency, event_date, settlement_date, status, linked_event_id, flexibility, minimum_allowed_amount.
- `request_payment_options.csv` — 790 rows. 2–4 options/request. full_payment vs installments; payment_amount, number_of_payments, first_payment_date, payment_frequency_days, financing_fee, total_payable_amount.
- `exchange_rates.csv` — 134 dated rows (from→to). Use rate for the cash event's settlement date + direction.
- `messages.csv` — 215 rows (some Indonesian). Employer payroll updates etc. related_event_id set only when it maps 1:1 to an event.
- `images.csv` — 16 rows → `dataset/media/images/<image_id>.png`. Fill blank event amounts. e.g. image_01 = payslip, Net Pay IDR 4,365,000.

## 4. Rules that bite (from problem_statement.md / AGENTS.md)
- `0 <= amount_safe_to_pay <= requested_amount` ALWAYS.
- `affordable_now` ⇒ `earliest_date_for_full_payment == request_date`, method full_payment, user accepts full_payment.
- `partial_payment` ⇒ status affordable_with_plan; only if allows_partial + user accepts + 0 < safe < requested + 2nd payment ≤ desired_completion_date. EXACTLY two payments summing to requested_amount (today: safe; earliest_date: remainder). Does NOT need to match an option.
- `installments` ⇒ must EXACTLY match a supplied payment option (dates via first_payment_date + frequency_days, amount = payment_amount).
- `spending_changes_needed` ⇒ ≤3 of `stop:<event_id>` / `reduce_to:<event_id>:<amt>`; ONLY non-protected flexible recurring expenses; stop & reduce must target different events.
- `earliest_date_for_full_payment` = first date full amount is safe as ONE payment WITHOUT optional spending changes; empty if never in forecast; independent of the user's method preference.
- Reserve pending debits; do NOT count pending credits/bonuses/refunds/gains until settled; count confirmed salary on settlement_date; do not invent income/expenses.
- Conflict resolution order: explicit cancellation/settlement/amendment → newer record same source → settled over estimate → financially safer interpretation.
- Plan ranking (when multiple safe & eligible): (1) completes by deadline, (2) no spending changes, (3) min total paid, (4) start earlier, (5) fewer payments, (6) lowest payment_option_id.
- Eligibility: an immediate method is eligible only if in `payment_methods_user_will_consider`; `wait` eligible if full payment becomes safe later AND user accepts full_payment; else `not_recommended`.
- Explanation style (from samples): grounded, short, states the low-point floor, e.g. "This leaves at least <min_balance> available." / "Paying earlier would take the balance below the <min> minimum."

## 5. AGENTS.md obligations (this repo)
- Maintain `log.txt` at repo root (gitignored). SESSION START + one entry per user turn. `tool=Claude Code`.
- Submission link (if asked): https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/submission
- `code.zip` must include `evaluation/usage_report.md` (providers, models, calls, in/out tokens, totals + per-request avg, est cost) for the final full run.

## 6. Subtask plan (each = one small, self-contained commit)
- [x] ST0  Repo hygiene: .gitignore, log.txt, PROJECT_MEMORY.md skeleton.
- [ ] ST1  Data profiling script + CSV loaders + typed models (learn value sets: event_type/status/flexibility).
- [ ] ST2  Currency conversion util (dated rate lookup, both directions).
- [ ] ST3  Image amount extraction (vision) → cached JSON; fill blank event amounts.
- [ ] ST4  Message interpretation (LLM) → cached structured amendments (salary change/date/cancel/reduce).
- [ ] ST5  Financial-state reconstruction (recurring detection, salary schedule, pending reserve, apply amendments + conflict rules).
- [ ] ST6  90-day forecast simulator + safety check (balance ≥ min every day).
- [ ] ST7  Solvers: amount_safe_to_pay + earliest_date_for_full_payment.
- [ ] ST8  Payment-option eligibility + plan enumeration + 6-tier ranking.
- [ ] ST9  Spending-changes search (flexible stop/reduce, ≤3).
- [ ] ST10 Decision assembler + grounded explanation generator.
- [ ] ST11 Deterministic validator (bounds, sums, schedule match, flexible-only, chronology, 250 rows).
- [ ] ST12 Self-scoring harness vs sample_requests.csv (25 golden).
- [ ] ST13 Full run → root output.csv; iterate to maximize sample score.
- [ ] ST14 evaluation/usage_report.md + README + package code.zip.

## 7. Decisions log
- 2026-09-12: Language = Python (matches starter `code/main.py`; best CSV+vision ecosystem). Committing on `main` of the fork (solo). Hybrid deterministic+LLM approach chosen for accuracy + low token cost.

## 8. Open questions / risks
- Exact numeric match of `amount_safe_to_pay` to hidden ground truth is the hard part — needs careful forecast semantics; iterate against the 25 samples.
- Recurrence detection heuristics (how many past occurrences ⇒ "recurring"; how to project next dates).
- Which LLM/provider for image + message extraction (affects usage_report). To confirm with user.

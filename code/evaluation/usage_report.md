# Token Usage and Cost Analysis

## Summary

The submitted solution that produces `output.csv` is a **fully deterministic Python
program** (`code/main.py`). The final full-dataset run makes **zero model/API calls** and
consumes **zero tokens**. All model usage was one-time, at build time, to pre-extract the 16
document images whose `amount` field is blank in `financial_events.csv`; those values are
cached in `code/evidence/image_amounts.json` and read deterministically at run time.

## Final full-dataset run (produces output.csv)

| Metric | Value |
|---|---|
| Model provider(s) | none (deterministic Python 3, standard library only) |
| Model name(s) | — |
| Model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Requests processed | 250 |
| Avg tokens / request | 0 |
| Estimated total cost | $0.00 |
| Estimated cost / request | $0.00 |
| Wall clock | < 1 s on a laptop |

Reproduce: `python3 code/main.py` → writes `output.csv` (250 rows). No network, no keys.

## One-time build-time extraction (NOT part of the reproducible run)

Only the **16 images** referenced by `dataset/images.csv` required a model, and only once.
A vision-capable model (Anthropic Claude, Opus-class, via the Claude Code harness) read each
PNG and extracted the single relevant figure (net pay, amount due, invoice total, etc.),
which was written to `code/evidence/image_amounts.json` with a source note per event. The
~215 `messages.csv` rows are handled by a deterministic bilingual (EN/ID) parser
(`code/lib/messages.py`) — **no model calls**.

| Metric | Value (approximate, build-time only) |
|---|---|
| Model provider | Anthropic |
| Model name | Claude (Opus-class, vision) |
| Model calls (image reads) | ~19 (16 images + 3 zoom-crops for low-resolution totals) |
| Est. input tokens | ~40,000 (image tokens + prompts) |
| Est. output tokens | ~2,500 |
| Est. total tokens | ~42,500 |
| Avg tokens / image | ~2,650 |
| Est. total cost | ~$0.30 (Opus-class list pricing; order-of-magnitude) |
| Est. cost / image | ~$0.02 |

These build-time figures are approximate and shown for transparency. They are **not**
incurred by the evaluated run: the cache makes the solution reproducible offline at zero
marginal token cost, and the 16 extracted amounts are fully auditable in
`code/evidence/image_amounts.json`.

## Why this design

Accuracy of the affordability decision is dominated by a deterministic 90-day cash-flow
forecast, not by language understanding. Restricting model usage to the small, bounded set
of image extractions (16) and caching the results gives the best accuracy at the lowest,
most predictable cost, and keeps every prediction reproducible and explainable.

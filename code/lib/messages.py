from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .models import Message, parse_date

_AMOUNT = re.compile(r"\b([A-Z]{3})\s*([\d][\d,]*(?:\.\d+)?)")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _amounts(text: str) -> list[tuple[str, float]]:
    out = []
    for cur, num in _AMOUNT.findall(text):
        out.append((cur, float(num.replace(",", ""))))
    return out


def _dates(text: str) -> list[date]:
    return [parse_date(d) for d in _DATE.findall(text)]


def _has(text: str, *words: str) -> bool:
    t = text.lower()
    return any(w in t for w in words)


@dataclass
class Effect:
    kind: str
    amount: float | None = None
    currency: str | None = None
    on_date: date | None = None
    pct: float | None = None
    note: str = ""


def classify(m: Message) -> Effect:
    """Map a (bilingual) template message to a structured forecast effect.
    Untrusted content: only amounts/dates/percentages and the template's
    financial meaning are used; embedded instructions are ignored."""
    t = m.message_text.replace("�", "'")
    low = t.lower()
    amts = _amounts(t)
    dts = _dates(t)
    amt = amts[0] if amts else (None, None)

    # ----- income endings -----
    if _has(low, "seasonal contract has ended", "no off-season income", "kontrak musiman"):
        return Effect("income_end", note="seasonal contract ended")

    # ----- salary date shift (no amount change) -----
    if _has(low, "now expected on", "replaces the payroll date", "revised date") and dts:
        return Effect("salary_date_shift", on_date=dts[-1], note="salary date shifted")

    # ----- salary amount amendments with an effective date -----
    if _has(low, "increased to", "naik menjadi") and amt[0]:
        d = dts[0] if dts else None
        return Effect("salary_from", amount=amt[1], currency=amt[0], on_date=d, note="salary increased")
    if _has(low, "resumes on", "resume on") and amt[0]:
        d = dts[0] if dts else None
        return Effect("salary_from", amount=amt[1], currency=amt[0], on_date=d, note="salary resumes")

    # ----- first salary from a new employer, confirmed on a date -----
    if _has(low, "first salary", "gaji pertama") and amt[0]:
        d = dts[0] if dts else None
        return Effect("salary_first", amount=amt[1], currency=amt[0], on_date=d, note="first salary new job")

    # ----- next-payroll salary amount (reduced / temporary / confirmed regular) -----
    if _has(low, "reduced to", "temporary monthly pay", "sementara", "next payroll is",
            "next salary", "regular salary for the next", "gaji pokok yang dikonfirmasi",
            "penggajian berikutnya adalah") and amt[0]:
        return Effect("salary_next", amount=amt[1], currency=amt[0], note="next salary amount")

    # ----- one household income source ended; remaining monthly is X -----
    if _has(low, "household", "rumah tangga") and _has(low, "ended", "berakhir") and amt[0]:
        return Effect("salary_next", amount=amt[1], currency=amt[0], note="remaining monthly income")

    # ----- salary confirmed (optionally stating the confirmed amount) -----
    if _has(low, "salary", "gaji", "payroll", "penggajian") and _has(low, "confirmed", "dikonfirmasi"):
        return Effect("salary_confirm", amount=amt[1], currency=amt[0], note="salary confirmed")

    # ----- rent increase by percentage on next payment -----
    if _has(low, "rent") and _PCT.search(t):
        return Effect("rent_increase_pct", pct=float(_PCT.search(t).group(1)), note="rent increased pct")

    # ----- everything else = do not alter the forecast -----
    # (pending refunds/payouts/prizes, unrealized portfolio, internal transfers,
    #  failed debits, bonuses/commissions pending) are handled by event status.
    return Effect("ignore", note="informational / status-handled")


def classify_all(messages: list[Message]) -> dict[str, Effect]:
    return {m.message_id: classify(m) for m in messages}

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


def parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def parse_dt(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_float(s: str) -> float | None:
    s = (s or "").strip()
    if s == "":
        return None
    return float(s)


def parse_int(s: str) -> int | None:
    s = (s or "").strip()
    if s == "":
        return None
    return int(float(s))


def parse_bool(s: str) -> bool:
    return (s or "").strip().lower() in ("true", "1", "yes")


def split_pipe(s: str) -> list[str]:
    s = (s or "").strip()
    if not s:
        return []
    return [p.strip() for p in s.split("|") if p.strip()]


@dataclass
class Profile:
    user_id: str
    home_currency: str
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: list[str]
    protect: list[str]
    willing_to_reduce: list[str]
    willing_to_stop: list[str]
    payment_methods: list[str]
    max_installment_months: int | None

    @classmethod
    def from_row(cls, r: dict) -> "Profile":
        return cls(
            user_id=r["user_id"],
            home_currency=r["home_currency"].strip(),
            current_available_balance=parse_float(r["current_available_balance"]) or 0.0,
            minimum_balance_to_keep=parse_float(r["minimum_balance_to_keep"]) or 0.0,
            financial_priorities=split_pipe(r["financial_priorities"]),
            protect=split_pipe(r["expense_categories_to_protect"]),
            willing_to_reduce=split_pipe(r["expense_categories_user_is_willing_to_reduce"]),
            willing_to_stop=split_pipe(r["expense_categories_user_is_willing_to_stop"]),
            payment_methods=split_pipe(r["payment_methods_user_will_consider"]),
            max_installment_months=parse_int(r["max_installment_months"]),
        )


@dataclass
class Event:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: float | None
    currency: str
    event_date: date | None
    settlement_date: date | None
    status: str
    linked_event_id: str | None
    flexibility: str
    minimum_allowed_amount: float | None

    @classmethod
    def from_row(cls, r: dict) -> "Event":
        return cls(
            event_id=r["event_id"],
            user_id=r["user_id"],
            event_type=r["event_type"].strip(),
            description=r["description"],
            category=r["category"].strip(),
            direction=r["direction"].strip(),
            amount=parse_float(r["amount"]),
            currency=r["currency"].strip(),
            event_date=parse_date(r["event_date"]),
            settlement_date=parse_date(r["settlement_date"]),
            status=r["status"].strip(),
            linked_event_id=(r["linked_event_id"].strip() or None),
            flexibility=r["flexibility"].strip(),
            minimum_allowed_amount=parse_float(r["minimum_allowed_amount"]),
        )

    @property
    def is_stoppable(self) -> bool:
        return self.flexibility in ("stoppable", "reducible_or_stoppable")

    @property
    def is_reducible(self) -> bool:
        return self.flexibility in ("reducible", "reducible_or_stoppable")


@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: float
    number_of_payments: int
    first_payment_date: date | None
    payment_frequency_days: int | None
    financing_fee: float
    total_payable_amount: float

    @classmethod
    def from_row(cls, r: dict) -> "PaymentOption":
        return cls(
            payment_option_id=r["payment_option_id"],
            request_id=r["request_id"],
            payment_method=r["payment_method"].strip(),
            payment_amount=parse_float(r["payment_amount"]) or 0.0,
            number_of_payments=parse_int(r["number_of_payments"]) or 1,
            first_payment_date=parse_date(r["first_payment_date"]),
            payment_frequency_days=parse_int(r["payment_frequency_days"]),
            financing_fee=parse_float(r["financing_fee"]) or 0.0,
            total_payable_amount=parse_float(r["total_payable_amount"]) or 0.0,
        )

    def schedule(self) -> list[date]:
        from datetime import timedelta

        if not self.first_payment_date:
            return []
        freq = self.payment_frequency_days or 0
        return [
            self.first_payment_date + timedelta(days=freq * i)
            for i in range(self.number_of_payments)
        ]


@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    desired_completion_date: date | None
    allows_partial_payment: bool
    request_text: str

    @classmethod
    def from_row(cls, r: dict) -> "Request":
        return cls(
            request_id=r["request_id"],
            user_id=r["user_id"],
            request_date=parse_date(r["request_date"]),
            request_type=r["request_type"].strip(),
            requested_amount=parse_float(r["requested_amount"]) or 0.0,
            desired_completion_date=parse_date(r["desired_completion_date"]),
            allows_partial_payment=parse_bool(r["allows_partial_payment"]),
            request_text=r["request_text"],
        )


@dataclass
class Message:
    message_id: str
    user_id: str
    request_id: str | None
    related_event_id: str | None
    sent_at: datetime | None
    source_type: str
    message_text: str

    @classmethod
    def from_row(cls, r: dict) -> "Message":
        return cls(
            message_id=r["message_id"],
            user_id=r["user_id"],
            request_id=(r["request_id"].strip() or None),
            related_event_id=(r["related_event_id"].strip() or None),
            sent_at=parse_dt(r["sent_at"]),
            source_type=r["source_type"].strip(),
            message_text=r["message_text"],
        )


@dataclass
class ImageLink:
    image_id: str
    user_id: str
    request_id: str
    related_event_id: str | None

    @classmethod
    def from_row(cls, r: dict) -> "ImageLink":
        return cls(
            image_id=r["image_id"],
            user_id=r["user_id"],
            request_id=(r["request_id"].strip() or None),
            related_event_id=(r["related_event_id"].strip() or None),
        )


@dataclass
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: float

    @classmethod
    def from_row(cls, r: dict) -> "ExchangeRate":
        return cls(
            rate_date=parse_date(r["rate_date"]),
            from_currency=r["from_currency"].strip(),
            to_currency=r["to_currency"].strip(),
            rate=parse_float(r["rate"]) or 0.0,
        )

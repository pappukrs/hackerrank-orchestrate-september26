from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field

from .evidence import load_image_amounts
from .models import (
    Event,
    ExchangeRate,
    ImageLink,
    Message,
    PaymentOption,
    Profile,
    Request,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")
IMAGES_DIR = os.path.join(DATASET_DIR, "media", "images")


def _read(name: str) -> list[dict]:
    path = os.path.join(DATASET_DIR, name)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


@dataclass
class Dataset:
    requests: list[Request]
    profiles_by_user: dict[str, Profile]
    events_by_user: dict[str, list[Event]]
    events_by_id: dict[str, Event]
    options_by_request: dict[str, list[PaymentOption]]
    messages_by_user: dict[str, list[Message]]
    messages_by_request: dict[str, list[Message]]
    messages_by_event: dict[str, list[Message]]
    images_by_event: dict[str, ImageLink]
    images_by_request: dict[str, list[ImageLink]]
    rates: list[ExchangeRate]
    requests_by_id: dict[str, Request] = field(default_factory=dict)

    def image_path(self, image_id: str) -> str:
        return os.path.join(IMAGES_DIR, f"{image_id}.png")


def load_dataset() -> Dataset:
    requests = [Request.from_row(r) for r in _read("requests.csv")]
    profiles = [Profile.from_row(r) for r in _read("financial_profiles.csv")]
    events = [Event.from_row(r) for r in _read("financial_events.csv")]

    image_amounts = load_image_amounts()
    for e in events:
        if e.amount is None and e.event_id in image_amounts:
            ev = image_amounts[e.event_id]
            e.amount = float(ev["amount"])
            if not e.currency and ev.get("currency"):
                e.currency = ev["currency"]
    options = [PaymentOption.from_row(r) for r in _read("request_payment_options.csv")]
    messages = [Message.from_row(r) for r in _read("messages.csv")]
    images = [ImageLink.from_row(r) for r in _read("images.csv")]
    rates = [ExchangeRate.from_row(r) for r in _read("exchange_rates.csv")]

    events_by_user: dict[str, list[Event]] = defaultdict(list)
    events_by_id: dict[str, Event] = {}
    for e in events:
        events_by_user[e.user_id].append(e)
        events_by_id[e.event_id] = e

    options_by_request: dict[str, list[PaymentOption]] = defaultdict(list)
    for o in options:
        options_by_request[o.request_id].append(o)

    messages_by_user: dict[str, list[Message]] = defaultdict(list)
    messages_by_request: dict[str, list[Message]] = defaultdict(list)
    messages_by_event: dict[str, list[Message]] = defaultdict(list)
    for m in messages:
        messages_by_user[m.user_id].append(m)
        if m.request_id:
            messages_by_request[m.request_id].append(m)
        if m.related_event_id:
            messages_by_event[m.related_event_id].append(m)

    images_by_event: dict[str, ImageLink] = {}
    images_by_request: dict[str, list[ImageLink]] = defaultdict(list)
    for im in images:
        if im.related_event_id:
            images_by_event[im.related_event_id] = im
        if im.request_id:
            images_by_request[im.request_id].append(im)

    ds = Dataset(
        requests=requests,
        profiles_by_user={p.user_id: p for p in profiles},
        events_by_user=events_by_user,
        events_by_id=events_by_id,
        options_by_request=options_by_request,
        messages_by_user=messages_by_user,
        messages_by_request=messages_by_request,
        messages_by_event=messages_by_event,
        images_by_event=images_by_event,
        images_by_request=images_by_request,
        rates=rates,
    )
    ds.requests_by_id = {r.request_id: r for r in requests}
    return ds

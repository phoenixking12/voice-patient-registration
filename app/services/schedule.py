from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Appointment
from app.services.patients import PatientError, utcnow

EASTERN = ZoneInfo("America/New_York")
PROVIDER = "Dr. Leena Shah, Internal Medicine"


def upcoming_slots(now: datetime | None = None, limit: int = 4) -> list[dict]:
    local_now = now.astimezone(EASTERN) if now else datetime.now(EASTERN)
    slots: list[dict] = []
    day = local_now.date() + timedelta(days=1)
    while len(slots) < limit:
        if day.weekday() < 5:
            for hour, clock in ((9, "9:00 AM"), (14, "2:00 PM")):
                start = datetime(day.year, day.month, day.day, hour, 0, tzinfo=EASTERN)
                label = f"{start.strftime('%A')}, {start.strftime('%B')} {start.day} at {clock} ET"
                slots.append(
                    {
                        "slot_id": start.strftime("%Y%m%dT%H%M"),
                        "starts_at": start.astimezone(timezone.utc).isoformat(),
                        "provider_name": PROVIDER,
                        "label": label,
                    }
                )
                if len(slots) >= limit:
                    break
        day += timedelta(days=1)
    return slots


def book_slot(db: Session, patient_id: str, slot_id: str) -> dict:
    from app.services.patients import _active

    _active(db, patient_id)
    match = next((slot for slot in upcoming_slots(limit=8) if slot["slot_id"] == slot_id), None)
    if match is None:
        raise PatientError("That appointment time is not open.", fields={"slot_id": "Pick one of the open times."})
    starts = datetime.fromisoformat(match["starts_at"]).astimezone(timezone.utc).replace(tzinfo=None)
    row = Appointment(
        patient_id=patient_id,
        slot_id=slot_id,
        starts_at=starts,
        provider_name=match["provider_name"],
        created_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "slot_id": row.slot_id,
        "starts_at": match["starts_at"],
        "provider_name": row.provider_name,
        "label": match["label"],
        "status": row.status,
    }


def list_appointments(db: Session, patient_id: str | None = None) -> list[dict]:
    query = db.query(Appointment)
    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    rows = query.order_by(Appointment.starts_at.asc()).all()
    slots = {slot["slot_id"]: slot for slot in upcoming_slots(limit=12)}
    result = []
    for row in rows:
        slot = slots.get(row.slot_id, {})
        result.append(
            {
                "id": row.id,
                "patient_id": row.patient_id,
                "slot_id": row.slot_id,
                "starts_at": row.starts_at.replace(tzinfo=timezone.utc).isoformat(),
                "provider_name": row.provider_name,
                "label": slot.get("label", row.slot_id),
                "status": row.status,
            }
        )
    return result


def pick_slot(text: str, slots: list[dict]) -> dict | None:
    lower = text.lower()
    morning = bool(re.search(r"\b(morning|9|nine)\b", lower))
    afternoon = bool(re.search(r"\b(afternoon|2|two)\b", lower))
    for slot in slots:
        weekday = slot["label"].split(",")[0].lower()
        if weekday not in lower:
            continue
        if morning and "9:00" in slot["label"]:
            return slot
        if afternoon and "2:00" in slot["label"]:
            return slot
        if not morning and not afternoon:
            return slot
    if morning:
        return next((slot for slot in slots if "9:00" in slot["label"]), None)
    if afternoon:
        return next((slot for slot in slots if "2:00" in slot["label"]), None)
    return None

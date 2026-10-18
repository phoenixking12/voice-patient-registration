from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CallLog
from app.services.patients import (
    PatientError,
    collected_from_row,
    create_patient,
    find_active_by_phone,
    format_dob,
    update_patient,
    utcnow,
)
from app.services.schedule import book_slot, pick_slot, upcoming_slots
from app.validation import REQUIRED_FIELDS, normalize_phone
from app.voice.extract import parse_utterance
from app.voice.llm import rephrase
from app.voice.prompt import FIELD_LABELS, say

logger = logging.getLogger("harbor.voice")

RESUME_WINDOW = timedelta(hours=2)


class SessionNotFound(Exception):
    pass


def start_session(db: Session, settings: Settings, caller_phone: str | None = None) -> dict:
    phone = _clean_caller(caller_phone)
    if phone:
        existing = _open_call(db, phone)
        if existing:
            state = json.loads(existing.state_json)
            missing = _next_missing(state)
            label = FIELD_LABELS.get(state.get("lang", "en"), FIELD_LABELS["en"]).get(missing or "first_name", "detail")
            line = say(state.get("lang", "en"), "resume", field=label)
            _append(existing, "agent", line)
            existing.updated_at = utcnow()
            db.commit()
            return _payload(existing, line, resumed=True)
        _drop_stale(db, phone)

    state = _fresh_state()
    line = say("en", "greeting")
    row = CallLog(
        caller_phone=phone,
        transcript=json.dumps([]),
        status="in_progress",
        phase=state["phase"],
        state_json=json.dumps(state),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(row)
    db.flush()
    _append(row, "agent", line)
    db.commit()
    logger.info("call %s started", row.id)
    return _payload(row, line, resumed=False)


def take_turn(db: Session, settings: Settings, session_id: str, text: str) -> dict:
    row = db.get(CallLog, session_id)
    if row is None:
        raise SessionNotFound(session_id)
    state = json.loads(row.state_json)
    _append(row, "caller", text)
    if state.get("phase") == "done" or row.status == "completed":
        line = say(state.get("lang", "en"), "closed")
        return _finish_turn(db, settings, row, state, line, ended=True)

    if _wants_restart(text):
        lang = state.get("lang", "en")
        state = _fresh_state()
        state["lang"] = lang
        line = say(lang, "restart")
        return _finish_turn(db, settings, row, state, line, ended=False)

    parsed = parse_utterance(text, state.get("pending"))
    if parsed.lang:
        state["lang"] = parsed.lang
    for key, value in parsed.fields.items():
        state["collected"][key] = value

    lang = state.get("lang", "en")
    if parsed.invalid:
        field, reason = next(iter(parsed.invalid.items()))
        state["pending"] = field
        line = say(lang, "reprompt", reason=reason)
        return _finish_turn(db, settings, row, state, line, ended=False)

    line, ended = _advance(db, state, text, parsed)
    return _finish_turn(db, settings, row, state, line, ended=ended)


def _advance(db: Session, state: dict, text: str, parsed) -> tuple[str, bool]:
    lang = state.get("lang", "en")
    phase = state["phase"]

    if phase == "duplicate":
        return _duplicate_phase(db, state, text, parsed), False
    if phase == "confirming":
        return _confirm_phase(db, state, parsed)
    if phase == "scheduling":
        return _schedule_phase(db, state, text, parsed)
    if phase == "collecting_changes":
        return _changes_phase(state, parsed), False
    if phase == "offer":
        return _offer_phase(state, parsed), False
    if phase == "collecting_optional":
        return _optional_phase(state, parsed), False

    duplicate = _maybe_duplicate(db, state)
    if duplicate:
        return duplicate, False
    return _collect_required(state), False


def _duplicate_phase(db: Session, state: dict, text: str, parsed) -> str:
    lang = state["lang"]
    name = state.get("candidate_name", "that patient")
    bare = text.strip().lower()
    agrees = parsed.yes or bool(re.match(r"^(yes|yeah|yep|update|that'?s me|si|sí)\b", bare))
    if agrees:
        from app.models import Patient

        row = db.get(Patient, state["candidate_id"])
        prefill = collected_from_row(row) if row else {}
        prefill.update(state["collected"])
        state["collected"] = prefill
        state["mode"] = "update"
        state["patient_id"] = state["candidate_id"]
        state["phase"] = "collecting_changes"
        state["pending"] = None
        return say(lang, "changes")
    if parsed.no:
        state["collected"].pop("phone_number", None)
        state["checked_phone"] = None
        state["phase"] = "collecting"
        state["pending"] = "phone_number"
        return say(lang, "duplicate_no")
    return say(lang, "duplicate_unsure", name=name)


def _confirm_phase(db: Session, state: dict, parsed) -> tuple[str, bool]:
    lang = state["lang"]
    if parsed.fields:
        return _readback(state, prefix=""), False
    if parsed.no:
        state["phase"] = "collecting_changes"
        state["pending"] = None
        return say(lang, "changes"), False
    if parsed.yes:
        return _save(db, state)
    return say(lang, "confirm_unsure"), False


def _changes_phase(state: dict, parsed) -> str:
    lang = state["lang"]
    if parsed.done or parsed.yes:
        state["phase"] = "confirming"
        return _readback(state)
    if parsed.fields:
        return say(lang, "changes_more")
    return say(lang, "changes")


def _offer_phase(state: dict, parsed) -> str:
    lang = state["lang"]
    if parsed.no or (parsed.done and not parsed.fields):
        state["phase"] = "confirming"
        return _readback(state)
    if parsed.yes or parsed.fields:
        state["phase"] = "collecting_optional"
        state["pending"] = None
        if parsed.fields:
            return say(lang, "optional_more")
        return say(lang, "optional_help")
    return say(lang, "offer")


def _optional_phase(state: dict, parsed) -> str:
    lang = state["lang"]
    if parsed.done or (parsed.no and not parsed.fields):
        state["phase"] = "confirming"
        return _readback(state)
    if parsed.fields:
        return say(lang, "optional_more")
    return say(lang, "optional_help")


def _schedule_phase(db: Session, state: dict, text: str, parsed) -> tuple[str, bool]:
    lang = state["lang"]
    slots = upcoming_slots(limit=4)
    if parsed.no or parsed.done:
        state["phase"] = "done"
        return say(lang, "goodbye"), True
    chosen = pick_slot(text, slots)
    if chosen is None and parsed.yes:
        chosen = slots[0]
    if chosen and state.get("patient_id"):
        booked = book_slot(db, state["patient_id"], chosen["slot_id"])
        state["phase"] = "done"
        state["appointment_id"] = booked["id"]
        line = say(lang, "booked", label=booked["label"], provider=booked["provider_name"])
        return f"{line} {say(lang, 'goodbye')}", True
    first = slots[0]["label"]
    second = slots[1]["label"]
    key = "schedule" if not state.get("offered_slots") else "schedule_again"
    state["offered_slots"] = True
    return say(lang, key, first=first, second=second), False


def _collect_required(state: dict) -> str:
    missing = _next_missing(state)
    if missing:
        state["phase"] = "collecting"
        state["pending"] = missing
        return say(state["lang"], missing)
    state["phase"] = "offer"
    state["pending"] = None
    return say(state["lang"], "offer")


def _maybe_duplicate(db: Session, state: dict) -> str | None:
    phone = state["collected"].get("phone_number")
    if not phone or state.get("mode") == "update" or state.get("checked_phone") == phone:
        return None
    state["checked_phone"] = phone
    existing = find_active_by_phone(db, phone)
    if existing is None:
        return None
    state["phase"] = "duplicate"
    state["candidate_id"] = existing.patient_id
    state["candidate_name"] = f"{existing.first_name} {existing.last_name}"
    state["pending"] = None
    return say(state["lang"], "duplicate", name=state["candidate_name"])


def _save(db: Session, state: dict) -> tuple[str, bool]:
    lang = state["lang"]
    payload = dict(state["collected"])
    try:
        if state.get("mode") == "update" and state.get("patient_id"):
            public = update_patient(db, state["patient_id"], payload)
        else:
            public = create_patient(db, payload)
    except PatientError as exc:
        state["phase"] = "collecting_changes"
        reason = next(iter(exc.fields.values()), exc.message)
        logger.info("call save failed %s", json.dumps({"error": exc.message, "fields": exc.fields}))
        return say(lang, "save_failed", reason=reason), False

    state["patient_id"] = public["patient_id"]
    state["phase"] = "scheduling"
    state["final_payload"] = public
    logger.info("patient_saved %s", json.dumps(public))
    slots = upcoming_slots(limit=2)
    saved = say(lang, "saved", name=public["first_name"])
    offer = say(lang, "schedule", first=slots[0]["label"], second=slots[1]["label"])
    state["offered_slots"] = True
    return f"{saved} {offer}", False


def _readback(state: dict, prefix: str = "") -> str:
    collected = state["collected"]
    phone = collected.get("phone_number", "")
    pretty_phone = f"({phone[0:3]}) {phone[3:6]}-{phone[6:]}" if len(phone) == 10 else phone
    bits = [
        f"{collected.get('first_name', '')} {collected.get('last_name', '')}".strip(),
        f"born {format_dob(collected['date_of_birth'])}" if collected.get("date_of_birth") else "",
        (collected.get("sex") or "").lower(),
        f"phone {pretty_phone}" if pretty_phone else "",
        f"at {collected.get('address_line_1', '')}",
    ]
    if collected.get("address_line_2"):
        bits.append(collected["address_line_2"])
    city_line = ", ".join(
        part for part in (collected.get("city"), collected.get("state"), collected.get("zip_code")) if part
    )
    if city_line:
        bits.append(city_line)
    if collected.get("email"):
        bits.append(f"email {collected['email']}")
    if collected.get("insurance_provider"):
        insurance = collected["insurance_provider"]
        if collected.get("insurance_member_id"):
            insurance += f", member {collected['insurance_member_id']}"
        bits.append(f"insurance {insurance}")
    if collected.get("emergency_contact_name"):
        bits.append(f"emergency contact {collected['emergency_contact_name']}")
    sentence = "Let me read that back. " + ", ".join(bit for bit in bits if bit) + "."
    if state.get("lang") == "es":
        sentence = "Te lo leo. " + ", ".join(bit for bit in bits if bit) + "."
    question = say(state["lang"], "confirm_ask")
    state["phase"] = "confirming"
    state["pending"] = None
    return f"{prefix}{sentence} {question}".strip()


def _finish_turn(db: Session, settings: Settings, row: CallLog, state: dict, line: str, ended: bool) -> dict:
    spoken = rephrase(settings, state.get("lang", "en"), line)
    _append(row, "agent", spoken)
    row.state_json = json.dumps(state)
    row.phase = state.get("phase", row.phase)
    row.patient_id = state.get("patient_id")
    row.updated_at = utcnow()
    if state.get("final_payload"):
        row.final_payload = json.dumps(state["final_payload"])
    if ended:
        row.status = "completed"
        row.ended_at = utcnow()
    db.commit()
    logger.info("call %s phase=%s caller_done=%s", row.id, row.phase, ended)
    return _payload(row, spoken, resumed=False, ended=ended)


def _payload(row: CallLog, line: str, *, resumed: bool, ended: bool | None = None) -> dict:
    state = json.loads(row.state_json)
    patient = None
    if state.get("final_payload"):
        patient = state["final_payload"]
    return {
        "session_id": row.id,
        "say": line,
        "phase": state.get("phase"),
        "collected": state.get("collected", {}),
        "ended": bool(ended) if ended is not None else row.status == "completed",
        "resumed": resumed,
        "patient": patient,
        "mode": state.get("mode", "create"),
    }


def _fresh_state() -> dict:
    return {
        "phase": "collecting",
        "lang": "en",
        "collected": {},
        "mode": "create",
        "patient_id": None,
        "pending": "first_name",
        "checked_phone": None,
        "candidate_id": None,
        "candidate_name": None,
        "offered_slots": False,
    }


def _next_missing(state: dict) -> str | None:
    collected = state.get("collected", {})
    for field in REQUIRED_FIELDS:
        if not collected.get(field):
            return field
    return None


def _append(row: CallLog, role: str, text: str) -> None:
    transcript = json.loads(row.transcript or "[]")
    transcript.append({"role": role, "text": text, "at": utcnow().isoformat() + "Z"})
    row.transcript = json.dumps(transcript)


def _open_call(db: Session, phone: str) -> CallLog | None:
    cutoff = utcnow() - RESUME_WINDOW
    return (
        db.query(CallLog)
        .filter(
            CallLog.caller_phone == phone,
            CallLog.status == "in_progress",
            CallLog.updated_at >= cutoff,
        )
        .order_by(CallLog.updated_at.desc())
        .first()
    )


def _drop_stale(db: Session, phone: str) -> None:
    cutoff = utcnow() - RESUME_WINDOW
    stale = (
        db.query(CallLog)
        .filter(CallLog.caller_phone == phone, CallLog.status == "in_progress", CallLog.updated_at < cutoff)
        .all()
    )
    for row in stale:
        row.status = "dropped"
        row.ended_at = utcnow()
    if stale:
        db.commit()


def _clean_caller(value: str | None) -> str | None:
    if not value:
        return None
    return normalize_phone(value)


def _wants_restart(text: str) -> bool:
    return bool(re.search(r"\b(start over|start again|begin again|scratch that|from the top)\b", text or "", re.I))


def calls_public(db: Session) -> list[dict]:
    rows = db.query(CallLog).order_by(CallLog.created_at.desc()).limit(50).all()
    result = []
    for row in rows:
        result.append(
            {
                "id": row.id,
                "caller_phone": row.caller_phone,
                "patient_id": row.patient_id,
                "status": row.status,
                "phase": row.phase,
                "transcript": json.loads(row.transcript or "[]"),
                "final_payload": json.loads(row.final_payload) if row.final_payload else None,
                "created_at": row.created_at.isoformat() + "Z",
                "updated_at": row.updated_at.isoformat() + "Z",
                "ended_at": row.ended_at.isoformat() + "Z" if row.ended_at else None,
            }
        )
    return result


def get_call(db: Session, call_id: str) -> dict | None:
    row = db.get(CallLog, call_id)
    if row is None:
        return None
    return calls_public_one(row)


def calls_public_one(row: CallLog) -> dict:
    return {
        "id": row.id,
        "caller_phone": row.caller_phone,
        "patient_id": row.patient_id,
        "status": row.status,
        "phase": row.phase,
        "transcript": json.loads(row.transcript or "[]"),
        "final_payload": json.loads(row.final_payload) if row.final_payload else None,
        "created_at": row.created_at.isoformat() + "Z",
        "updated_at": row.updated_at.isoformat() + "Z",
        "ended_at": row.ended_at.isoformat() + "Z" if row.ended_at else None,
    }

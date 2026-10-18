from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.models import CallLog
from app.services.patients import PatientError, create_patient, find_active_by_phone, update_patient, utcnow
from app.services.schedule import book_slot, upcoming_slots
from app.voice.prompt import SYSTEM_PROMPT

logger = logging.getLogger("harbor.vapi")


def handle_vapi(db: Session, payload: dict) -> dict:
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        message = payload if isinstance(payload, dict) else {}
    kind = message.get("type") or payload.get("type")
    logger.info("vapi event %s", kind)

    if kind in {"tool-calls", "tool-call", "function-call"}:
        calls = (
            message.get("toolCallList")
            or message.get("toolCalls")
            or message.get("toolWithToolCallList")
            or []
        )
        if kind == "function-call" and message.get("functionCall"):
            calls = [message["functionCall"]]
        results = []
        for call in calls:
            name, args, call_id = _unpack(call)
            text = _dispatch(db, name, args)
            results.append({"toolCallId": call_id, "result": text})
        return {"results": results}

    if kind == "end-of-call-report":
        _store_report(db, message)
        return {"ok": True}

    return {"ok": True}


def _dispatch(db: Session, name: str, args: dict) -> str:
    try:
        if name == "lookup_patient":
            return _lookup(db, args)
        if name == "create_patient":
            return _create(db, args)
        if name == "update_patient":
            return _update(db, args)
        if name == "list_appointment_slots":
            slots = upcoming_slots(limit=4)
            return "Open times: " + "; ".join(f"{slot['slot_id']} {slot['label']}" for slot in slots)
        if name == "book_appointment":
            booked = book_slot(db, str(args.get("patient_id") or ""), str(args.get("slot_id") or ""))
            return f"Booked {booked['label']} with {booked['provider_name']}."
        return f"Unknown tool {name}."
    except PatientError as exc:
        detail = "; ".join(f"{key}: {value}" for key, value in exc.fields.items()) or exc.message
        logger.info("vapi tool %s rejected %s", name, detail)
        return f"Not saved. {detail} Ask only for the field that failed."
    except Exception:
        logger.exception("vapi tool %s failed", name)
        return "The write failed on our side. Apologize and ask the caller to repeat the last answer."


def _lookup(db: Session, args: dict) -> str:
    phone = str(args.get("phone_number") or "")
    row = find_active_by_phone(db, phone)
    if row is None:
        return "No patient is registered with that phone number."
    return (
        f"Existing patient {row.first_name} {row.last_name}, id {row.patient_id}, "
        f"born {row.date_of_birth.strftime('%m/%d/%Y')}, phone {row.phone_number}. "
        "Ask if they want to update this record before changing anything."
    )


def _create(db: Session, args: dict) -> str:
    public = create_patient(db, args)
    logger.info("patient_saved %s", json.dumps(public))
    return (
        f"Saved. patient_id {public['patient_id']}. "
        f"Tell {public['first_name']} they are all set, then offer an appointment."
    )


def _update(db: Session, args: dict) -> str:
    patient_id = str(args.get("patient_id") or "")
    fields = {key: value for key, value in args.items() if key != "patient_id"}
    public = update_patient(db, patient_id, fields)
    logger.info("patient_saved %s", json.dumps(public))
    return f"Updated patient {public['patient_id']}. Read the change back before you end the call."


def _store_report(db: Session, message: dict) -> None:
    artifact = message.get("artifact") or {}
    transcript = artifact.get("transcript") or ""
    call = message.get("call") or {}
    customer = call.get("customer") or {}
    number = customer.get("number")
    row = CallLog(
        caller_phone=None,
        transcript=json.dumps([{"role": "report", "text": transcript, "at": utcnow().isoformat() + "Z"}]),
        final_payload=json.dumps({"ended_reason": message.get("endedReason"), "summary": artifact.get("summary")}),
        status="completed",
        phase="report",
        state_json=json.dumps({"source": "vapi", "caller": number}),
        created_at=utcnow(),
        updated_at=utcnow(),
        ended_at=utcnow(),
    )
    db.add(row)
    db.commit()
    logger.info("vapi end-of-call stored %s", row.id)


def _unpack(call: dict) -> tuple[str, dict, str]:
    if not isinstance(call, dict):
        return "", {}, ""
    function = call.get("function") or {}
    name = function.get("name") or call.get("name") or ""
    raw_args = function.get("arguments", None)
    if raw_args is None:
        raw_args = call.get("parameters", call.get("arguments", {}))
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args or "{}")
        except json.JSONDecodeError:
            raw_args = {}
    if not isinstance(raw_args, dict):
        raw_args = {}
    call_id = call.get("id") or call.get("toolCallId") or name
    return name, raw_args, str(call_id)


def assistant_stub(public_base_url: str) -> dict:
    """Small helper so /voice/vapi/assistant shows the URL the dashboard should use."""
    base = public_base_url.rstrip("/")
    return {
        "name": "Harbor Intake",
        "server_url": f"{base}/voice/vapi",
        "system_prompt": SYSTEM_PROMPT,
        "note": "Import vapi/assistant.json and replace REPLACE_WITH_PUBLIC_URL.",
    }

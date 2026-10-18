from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Patient
from app.validation import normalize_patient, normalize_phone, parse_dob


class PatientError(Exception):
    def __init__(self, message: str, *, fields: dict | None = None, status: int = 422):
        self.message = message
        self.fields = fields or {}
        self.status = status
        super().__init__(message)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_patient(db: Session, data: dict) -> dict:
    clean, errors = normalize_patient(data, partial=False)
    if errors:
        raise PatientError("Some fields need another look.", fields=errors, status=422)
    _reject_active_phone(db, clean["phone_number"])
    now = utcnow()
    row = Patient(created_at=now, updated_at=now, **clean)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise PatientError(
            "A patient with this phone number already exists.",
            fields={"phone_number": "Already registered. Update that record instead."},
        ) from exc
    db.refresh(row)
    return to_public(row)


def update_patient(db: Session, patient_id: str, data: dict) -> dict:
    if not data:
        raise PatientError("Provide at least one field to update.", status=400)
    row = _active(db, patient_id)
    clean, errors = normalize_patient(data, partial=True)
    if errors:
        raise PatientError("Some fields need another look.", fields=errors, status=422)
    if "phone_number" in clean and clean["phone_number"] != row.phone_number:
        _reject_active_phone(db, clean["phone_number"], ignore_id=row.patient_id)
    for key, value in clean.items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise PatientError(
            "A patient with this phone number already exists.",
            fields={"phone_number": "Already registered. Update that record instead."},
        ) from exc
    db.refresh(row)
    return to_public(row)


def get_patient(db: Session, patient_id: str) -> dict:
    return to_public(_active(db, patient_id))


def soft_delete(db: Session, patient_id: str) -> dict:
    row = _active(db, patient_id)
    row.deleted_at = utcnow()
    row.updated_at = row.deleted_at
    db.commit()
    db.refresh(row)
    return to_public(row)


def list_patients(
    db: Session,
    *,
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
) -> list[dict]:
    query = db.query(Patient).filter(Patient.deleted_at.is_(None))
    if last_name:
        query = query.filter(func.lower(Patient.last_name) == last_name.strip().lower())
    if date_of_birth:
        parsed, err = parse_dob(date_of_birth)
        if err or parsed is None:
            raise PatientError(err or "Invalid date of birth.", fields={"date_of_birth": err or "Invalid."})
        query = query.filter(Patient.date_of_birth == parsed)
    if phone_number:
        phone = normalize_phone(phone_number)
        if not phone:
            raise PatientError(
                "Use a 10-digit U.S. number.",
                fields={"phone_number": "Use a 10-digit U.S. number."},
            )
        query = query.filter(Patient.phone_number == phone)
    rows = query.order_by(Patient.created_at.asc()).limit(200).all()
    return [to_public(row) for row in rows]


def find_active_by_phone(db: Session, phone_number: str) -> Patient | None:
    phone = normalize_phone(phone_number) or phone_number
    return (
        db.query(Patient)
        .filter(Patient.phone_number == phone, Patient.deleted_at.is_(None))
        .one_or_none()
    )


def collected_from_row(row: Patient) -> dict:
    data = {
        "first_name": row.first_name,
        "last_name": row.last_name,
        "date_of_birth": row.date_of_birth.isoformat(),
        "sex": row.sex,
        "phone_number": row.phone_number,
        "email": row.email,
        "address_line_1": row.address_line_1,
        "address_line_2": row.address_line_2,
        "city": row.city,
        "state": row.state,
        "zip_code": row.zip_code,
        "insurance_provider": row.insurance_provider,
        "insurance_member_id": row.insurance_member_id,
        "preferred_language": row.preferred_language,
        "emergency_contact_name": row.emergency_contact_name,
        "emergency_contact_phone": row.emergency_contact_phone,
    }
    return {key: value for key, value in data.items() if value not in (None, "")}


def to_public(row: Patient) -> dict:
    return {
        "patient_id": row.patient_id,
        "first_name": row.first_name,
        "last_name": row.last_name,
        "date_of_birth": row.date_of_birth.strftime("%m/%d/%Y"),
        "sex": row.sex,
        "phone_number": row.phone_number,
        "email": row.email,
        "address_line_1": row.address_line_1,
        "address_line_2": row.address_line_2,
        "city": row.city,
        "state": row.state,
        "zip_code": row.zip_code,
        "insurance_provider": row.insurance_provider,
        "insurance_member_id": row.insurance_member_id,
        "preferred_language": row.preferred_language,
        "emergency_contact_name": row.emergency_contact_name,
        "emergency_contact_phone": row.emergency_contact_phone,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "deleted_at": _iso(row.deleted_at),
    }


def seed_demo(db: Session) -> None:
    if db.query(Patient).count():
        return
    samples = [
        {
            "first_name": "Jane",
            "last_name": "Adler",
            "date_of_birth": "04/12/1986",
            "sex": "Female",
            "phone_number": "512-555-2198",
            "email": "jane.adler@example.com",
            "address_line_1": "18 Barton Springs Rd",
            "city": "Austin",
            "state": "TX",
            "zip_code": "78704",
            "insurance_provider": "Aetna",
            "insurance_member_id": "AET100200",
            "preferred_language": "English",
        },
        {
            "first_name": "Carlos",
            "last_name": "Reyes",
            "date_of_birth": "11/02/1979",
            "sex": "Male",
            "phone_number": "737-555-2184",
            "address_line_1": "402 South Congress Ave",
            "address_line_2": "Apt 3",
            "city": "Austin",
            "state": "Texas",
            "zip_code": "78704",
            "preferred_language": "Spanish",
            "emergency_contact_name": "Lucia Reyes",
            "emergency_contact_phone": "737-555-2188",
        },
    ]
    for sample in samples:
        create_patient(db, sample)


def _active(db: Session, patient_id: str) -> Patient:
    row = (
        db.query(Patient)
        .filter(Patient.patient_id == patient_id, Patient.deleted_at.is_(None))
        .one_or_none()
    )
    if row is None:
        raise PatientError("No active patient with that id.", status=404)
    return row


def _reject_active_phone(db: Session, phone: str, ignore_id: str | None = None) -> None:
    existing = find_active_by_phone(db, phone)
    if existing and existing.patient_id != ignore_id:
        raise PatientError(
            "A patient with this phone number already exists.",
            fields={"phone_number": "Already registered. Update that record instead."},
        )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def format_dob(value: date | str) -> str:
    if isinstance(value, str):
        parsed, _err = parse_dob(value)
        if parsed is None:
            return value
        value = parsed
    return f"{value.strftime('%B')} {value.day}, {value.year}"

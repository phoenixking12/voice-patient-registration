from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid.uuid4())


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint(
            "sex IN ('Male', 'Female', 'Other', 'Decline to Answer')",
            name="ck_patients_sex",
        ),
        CheckConstraint("length(phone_number) BETWEEN 8 AND 16", name="ck_patients_phone"),
        CheckConstraint("length(state) = 2", name="ck_patients_state"),
        Index("ix_patients_last_name", "last_name"),
        Index("ix_patients_dob", "date_of_birth"),
        # A deleted row must not block the same number from registering again.
        Index(
            "uq_patients_phone_active",
            "phone_number",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    patient_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    address_line_1: Mapped[str] = mapped_column(String(120), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    insurance_provider: Mapped[str | None] = mapped_column(String(80))
    insurance_member_id: Mapped[str | None] = mapped_column(String(40))
    preferred_language: Mapped[str] = mapped_column(String(40), nullable=False, default="English")
    emergency_contact_name: Mapped[str | None] = mapped_column(String(80))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    caller_phone: Mapped[str | None] = mapped_column(String(20))
    patient_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("patients.patient_id"))
    transcript: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    final_payload: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    phase: Mapped[str] = mapped_column(String(40), nullable=False, default="collecting")
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.patient_id"), nullable=False)
    slot_id: Mapped[str] = mapped_column(String(40), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="booked")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

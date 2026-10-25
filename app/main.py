from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_engine, make_session_factory, relax_phone_check
from app.models import Base
from app.services.patients import PatientError, create_patient, get_patient, list_patients, seed_demo, soft_delete, update_patient
from app.services.schedule import list_appointments
from app.validation import normalize_phone
from app.voice.agent import SessionNotFound, calls_public, get_call, start_session, take_turn
from app.voice.vapi import assistant_stub, handle_vapi
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("harbor")
STATIC = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    relax_phone_check(engine)
    factory = make_session_factory(engine)
    if settings.seed:
        with factory() as db:
            seed_demo(db)

    app = FastAPI(
        title="Harbor Intake",
        version="1.0.0",
        description="Voice patient registration. The phone agent and the REST API share one database.",
    )
    app.state.settings = settings
    app.state.session_factory = factory

    def get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    def ok(data, status: int = 200) -> JSONResponse:
        return JSONResponse({"data": data, "error": None}, status_code=status)

    def fail(status: int, code: str, message: str, fields: dict | None = None) -> JSONResponse:
        error = {"code": code, "message": message}
        if fields:
            error["fields"] = fields
        return JSONResponse({"data": None, "error": error}, status_code=status)

    @app.exception_handler(RequestValidationError)
    async def _bad_json(_request: Request, _exc: RequestValidationError):
        return fail(400, "bad_request", "The request body is not valid JSON.")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = "not_found" if exc.status_code == 404 else "bad_request"
        return fail(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, exc: Exception):
        logger.exception("unhandled error")
        return fail(500, "server_error", "Something went wrong on our side.")

    @app.get("/health")
    def health():
        return ok(
            {
                "status": "ok",
                "voice_mode": settings.voice_mode,
                "database": settings.database_url.split(":", 1)[0],
                "public_base_url": settings.public_base_url,
            }
        )

    @app.get("/patients")
    def patients(
        last_name: str | None = None,
        date_of_birth: str | None = None,
        phone_number: str | None = None,
        db: Session = Depends(get_db),
    ):
        try:
            rows = list_patients(db, last_name=last_name, date_of_birth=date_of_birth, phone_number=phone_number)
        except PatientError as exc:
            return fail(exc.status, "validation_error", exc.message, exc.fields)
        return ok({"patients": rows})

    @app.get("/patients/{patient_id}")
    def one_patient(patient_id: str, db: Session = Depends(get_db)):
        try:
            return ok(get_patient(db, patient_id))
        except PatientError as exc:
            return fail(exc.status, "not_found", exc.message)

    @app.post("/patients")
    async def post_patient(request: Request, db: Session = Depends(get_db)):
        payload, error = await _json_object(request)
        if error:
            return error
        try:
            created = create_patient(db, payload)
        except PatientError as exc:
            code = "validation_error" if exc.status == 422 else "bad_request"
            return fail(exc.status, code, exc.message, exc.fields)
        logger.info("patient_saved %s", created["patient_id"])
        return ok(created, 201)

    @app.put("/patients/{patient_id}")
    async def put_patient(patient_id: str, request: Request, db: Session = Depends(get_db)):
        payload, error = await _json_object(request)
        if error:
            return error
        try:
            updated = update_patient(db, patient_id, payload)
        except PatientError as exc:
            code = "not_found" if exc.status == 404 else "validation_error" if exc.status == 422 else "bad_request"
            return fail(exc.status, code, exc.message, exc.fields or None)
        return ok(updated)

    @app.delete("/patients/{patient_id}")
    def delete_patient(patient_id: str, db: Session = Depends(get_db)):
        try:
            return ok(soft_delete(db, patient_id))
        except PatientError as exc:
            return fail(exc.status, "not_found", exc.message)

    @app.get("/appointments")
    def appointments(patient_id: str | None = None, db: Session = Depends(get_db)):
        return ok({"appointments": list_appointments(db, patient_id)})

    @app.get("/calls")
    def calls(db: Session = Depends(get_db)):
        return ok({"calls": calls_public(db)})

    @app.get("/calls/{call_id}")
    def one_call(call_id: str, db: Session = Depends(get_db)):
        row = get_call(db, call_id)
        if row is None:
            return fail(404, "not_found", "No call with that id.")
        return ok(row)

    @app.post("/voice/sessions")
    async def open_session(request: Request, db: Session = Depends(get_db)):
        payload, error = await _json_object(request, allow_empty=True)
        if error:
            return error
        caller = payload.get("caller_phone")
        if caller and not normalize_phone(str(caller)):
            return fail(422, "validation_error", "That caller phone number is not valid.", {"caller_phone": "Invalid."})
        opened = start_session(db, settings, caller_phone=caller)
        return ok(opened, 201)

    @app.post("/voice/sessions/{session_id}/turns")
    async def turn(session_id: str, request: Request, db: Session = Depends(get_db)):
        payload, error = await _json_object(request)
        if error:
            return error
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return fail(422, "validation_error", "Say something and I'll keep going.", {"text": "Required."})
        try:
            result = take_turn(db, settings, session_id, text.strip())
        except SessionNotFound:
            return fail(404, "not_found", "That call session does not exist.")
        return ok(result)

    @app.post("/voice/vapi")
    async def vapi(request: Request, db: Session = Depends(get_db)):
        payload, error = await _json_object(request)
        if error:
            return error
        return JSONResponse(handle_vapi(db, payload))

    @app.get("/voice/vapi/assistant")
    def assistant():
        return ok(assistant_stub(settings.public_base_url))

    @app.get("/")
    def desk():
        return FileResponse(STATIC / "desk.html")

    @app.get("/dashboard")
    def dashboard():
        return FileResponse(STATIC / "registry.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    async def _json_object(request: Request, allow_empty: bool = False):
        raw = await request.body()
        if not raw:
            if allow_empty:
                return {}, None
            return None, fail(400, "bad_request", "The body must be a JSON object.")
        try:
            payload = await request.json()
        except Exception:
            return None, fail(400, "bad_request", "The body must be JSON.")
        if not isinstance(payload, dict):
            return None, fail(400, "bad_request", "The body must be a JSON object.")
        return payload, None

    return app


app = create_app()

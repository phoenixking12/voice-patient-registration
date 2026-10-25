from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(connection, _record):  # noqa: ANN001
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def relax_phone_check(engine: Engine) -> None:
    """Drop the old 10-digit U.S.-only check so an existing database can store other countries."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'patients'")
        ).fetchone()
        if row is None or not row[0] or "length(phone_number) = 10" not in row[0]:
            return
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("ALTER TABLE patients RENAME TO patients_old"))
    from app.models import Base

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO patients SELECT * FROM patients_old"))
        connection.execute(text("DROP TABLE patients_old"))
        connection.execute(text("PRAGMA foreign_keys=ON"))

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database_url="sqlite:///" + tmp_path.joinpath("test.db").as_posix(),
        seed=False,
        llm_enabled=False,
    )
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def seeded_client(tmp_path):
    settings = Settings(
        database_url="sqlite:///" + tmp_path.joinpath("seed.db").as_posix(),
        seed=True,
        llm_enabled=False,
    )
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client


PRIYA = {
    "first_name": "Priya",
    "last_name": "Shah",
    "date_of_birth": "07/15/1988",
    "sex": "Female",
    "phone_number": "512-555-2199",
    "address_line_1": "88 Congress Avenue",
    "city": "Austin",
    "state": "TX",
    "zip_code": "78701",
}


def talk(client: TestClient, lines: list[str], caller_phone: str | None = None) -> list[dict]:
    body = {} if not caller_phone else {"caller_phone": caller_phone}
    opened = client.post("/voice/sessions", json=body)
    assert opened.status_code == 201, opened.text
    session_id = opened.json()["data"]["session_id"]
    turns = [opened.json()["data"]]
    for line in lines:
        response = client.post(f"/voice/sessions/{session_id}/turns", json={"text": line})
        assert response.status_code == 200, response.text
        turns.append(response.json()["data"])
    return turns

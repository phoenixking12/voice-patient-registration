from __future__ import annotations

from tests.conftest import PRIYA


def test_health_envelope(client):
    response = client.get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["error"] is None
    assert body["data"]["status"] == "ok"
    assert body["data"]["voice_mode"] == "script"


def test_create_get_filter_update_and_soft_delete(client):
    created = client.post("/patients", json=PRIYA)
    assert created.status_code == 201
    patient = created.json()["data"]
    assert created.json()["error"] is None
    assert patient["date_of_birth"] == "07/15/1988"
    assert patient["phone_number"] == "5125552199"
    assert patient["state"] == "TX"
    assert patient["preferred_language"] == "English"
    assert patient["deleted_at"] is None

    fetched = client.get(f"/patients/{patient['patient_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["first_name"] == "Priya"

    listed = client.get("/patients", params={"last_name": "shah", "phone_number": "(512) 555-2199"})
    assert listed.status_code == 200
    assert len(listed.json()["data"]["patients"]) == 1

    updated = client.put(
        f"/patients/{patient['patient_id']}",
        json={"email": "priya.shah@example.com", "address_line_2": "Apt 4"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["email"] == "priya.shah@example.com"
    assert updated.json()["data"]["last_name"] == "Shah"

    removed = client.delete(f"/patients/{patient['patient_id']}")
    assert removed.status_code == 200
    assert removed.json()["data"]["deleted_at"] is not None
    assert client.get(f"/patients/{patient['patient_id']}").status_code == 404
    assert client.get("/patients").json()["data"]["patients"] == []

    again = client.post("/patients", json=PRIYA)
    assert again.status_code == 201


def test_validation_and_duplicate_phone(client):
    bad = client.post("/patients", json={**PRIYA, "date_of_birth": "01/01/2099", "zip_code": "12"})
    assert bad.status_code == 422
    fields = bad.json()["error"]["fields"]
    assert "date_of_birth" in fields
    assert "zip_code" in fields

    assert client.post("/patients", content=b"not-json", headers={"content-type": "application/json"}).status_code == 400
    assert client.post("/patients", json=[]).status_code == 400
    assert client.get("/patients/missing").status_code == 404
    assert client.put("/patients/missing", json={"city": "Austin"}).status_code == 404

    first = client.post("/patients", json=PRIYA)
    assert first.status_code == 201
    duplicate = client.post("/patients", json={**PRIYA, "first_name": "Anita"})
    assert duplicate.status_code == 422
    assert "phone_number" in duplicate.json()["error"]["fields"]


def test_seed_records_exist(seeded_client):
    rows = seeded_client.get("/patients").json()["data"]["patients"]
    last_names = {row["last_name"] for row in rows}
    assert {"Adler", "Reyes"} <= last_names


def test_vapi_tool_saves_and_rejects(client):
    rejected = client.post(
        "/voice/vapi",
        json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {"id": "t1", "name": "create_patient", "parameters": {"first_name": "No"}}
                ],
            }
        },
    )
    assert rejected.status_code == 200
    assert "Not saved" in rejected.json()["results"][0]["result"]
    assert client.get("/patients").json()["data"]["patients"] == []

    saved = client.post(
        "/voice/vapi",
        json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [{"id": "t2", "name": "create_patient", "parameters": PRIYA}],
            }
        },
    )
    assert "Saved" in saved.json()["results"][0]["result"]
    rows = client.get("/patients").json()["data"]["patients"]
    assert rows[0]["last_name"] == "Shah"

    lookup = client.post(
        "/voice/vapi",
        json={
            "message": {
                "type": "tool-calls",
                "toolCalls": [
                    {
                        "id": "t3",
                        "function": {"name": "lookup_patient", "arguments": {"phone_number": "512-555-2199"}},
                    }
                ],
            }
        },
    )
    assert "Priya Shah" in lookup.json()["results"][0]["result"]

from __future__ import annotations

from tests.conftest import talk


FULL = [
    "Priya Shah",
    "July 15, 1988",
    "female",
    "512-555-2199",
    "88 Congress Avenue",
    "Austin",
    "Texas",
    "78701",
    "no thanks",
    "yes",
    "no",
]


def test_full_registration_persists(client):
    turns = talk(client, FULL)
    assert turns[-1]["ended"] is True
    assert turns[-1]["patient"]["first_name"] == "Priya"
    assert "all set" in turns[-2]["say"].lower() or "you're all set" in turns[-2]["say"].lower()
    listed = client.get("/patients", params={"last_name": "Shah"})
    assert listed.json()["data"]["patients"][0]["phone_number"] == "5125552199"
    calls = client.get("/calls").json()["data"]["calls"]
    assert calls[0]["status"] == "completed"
    assert calls[0]["final_payload"]["last_name"] == "Shah"


def test_one_sentence_then_confirm(client):
    turns = talk(
        client,
        [
            "My name is Priya Shah, date of birth 07/15/1988, female, phone 512-555-2199, I live at 88 Congress Avenue, Austin, Texas 78701.",
            "no thanks",
            "yes",
            "no",
        ],
    )
    assert turns[1]["collected"]["city"] == "Austin"
    assert turns[1]["collected"]["state"] == "TX"
    assert turns[1]["phase"] == "offer"
    assert turns[2]["phase"] == "confirming"
    assert turns[-1]["patient"]["zip_code"] == "78701"


def test_chat_accepts_month_day_year(client):
    turns = talk(client, ["Priya Shah", "03/04/1990"])
    assert "month/day/year" in turns[1]["say"]
    assert turns[-1]["collected"]["date_of_birth"] == "1990-03-04"


def test_chat_accepts_a_day_that_cannot_be_a_month(client):
    turns = talk(client, ["Priya Shah", "25/10/1990"])
    assert turns[-1]["collected"]["date_of_birth"] == "1990-10-25"


def test_chat_accepts_a_non_us_phone(client):
    turns = talk(client, ["Priya Shah", "03/04/1990", "female", "+92 300 5550199"])
    assert turns[-1]["collected"]["phone_number"] == "+923005550199"


def test_future_birthday_is_rejected(client):
    turns = talk(client, ["Priya Shah", "January 1, 2099"])
    assert "date_of_birth" not in turns[-1]["collected"]
    assert "future" in turns[-1]["say"].lower()


def test_short_phone_is_reprompted(client):
    turns = talk(client, ["Priya Shah", "July 15, 1988", "female", "555"])
    assert "phone_number" not in turns[-1]["collected"]
    assert "10" in turns[-1]["say"]


def test_spelled_correction_before_save(client):
    turns = talk(
        client,
        [
            "My name is Priya Shah, date of birth 07/15/1988, female, phone 512-555-2199, I live at 88 Congress Avenue, Austin, Texas 78701.",
            "no thanks",
            "my last name is spelled D-A-V-I-S",
            "yes",
            "no",
        ],
    )
    assert turns[3]["collected"]["last_name"] == "Davis"
    assert turns[3]["phase"] == "confirming"
    assert turns[-1]["patient"]["last_name"] == "Davis"


def test_start_over_clears_the_call(client):
    turns = talk(client, ["Priya Shah", "start over"])
    assert turns[-1]["collected"] == {}
    assert "start fresh" in turns[-1]["say"].lower() or "empezamos" in turns[-1]["say"].lower()


def test_duplicate_phone_offers_update(client):
    created = client.post(
        "/patients",
        json={
            "first_name": "Jane",
            "last_name": "Adler",
            "date_of_birth": "04/12/1986",
            "sex": "Female",
            "phone_number": "512-555-2198",
            "address_line_1": "18 Barton Springs Rd",
            "city": "Austin",
            "state": "TX",
            "zip_code": "78704",
        },
    )
    assert created.status_code == 201
    turns = talk(client, ["My phone number is 512-555-2198"])
    assert turns[-1]["phase"] == "duplicate"
    assert "Jane Adler" in turns[-1]["say"]

    updated = talk(
        client,
        [
            "My phone number is 512-555-2198",
            "yes",
            "my email is jane.adler@example.com",
            "that's all",
            "yes",
            "no",
        ],
    )
    assert updated[-1]["patient"]["email"] == "jane.adler@example.com"
    assert updated[-1]["mode"] == "update"
    assert len(client.get("/patients").json()["data"]["patients"]) == 1


def test_spanish_switch(client):
    turns = talk(client, ["Hablo español"])
    assert turns[-1]["collected"]["preferred_language"] == "Spanish"
    assert "nombre" in turns[-1]["say"].lower()


def test_yes_books_the_first_open_slot(client):
    turns = talk(client, FULL[:-1] + ["yes"])
    assert turns[-1]["ended"] is True
    appointments = client.get("/appointments").json()["data"]["appointments"]
    assert len(appointments) == 1
    assert appointments[0]["provider_name"].startswith("Dr. Leena Shah")

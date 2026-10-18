# Harbor Intake

A voice patient-registration desk. A caller gives their demographics in a normal conversation. The desk checks each field, reads the record back, and saves it. The same record is available from a REST API and a small registry page.

This is a demo for a hiring review. Use fictional people only. It is not a production clinic system and it does not try to be HIPAA compliant.

The original assignment file is not in this repository. It was marked confidential for the candidate. This page describes the system that was built.

## Try it with no accounts

You can register a patient, search the registry, and talk to the desk before you create a single vendor account.

```powershell
cd D:\carecloud-patient-registration
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Then open:

| Page | What it is |
|---|---|
| http://127.0.0.1:8000 | Call desk. Type, or use the mic in Chrome. The reply is also spoken. |
| http://127.0.0.1:8000/dashboard | Registry. Search, create, and soft-delete. |
| http://127.0.0.1:8000/docs | Interactive API. |
| http://127.0.0.1:8000/health | Tells you whether a language-model key is loaded. |

Two fictional patients are inserted the first time the database is empty: Jane Adler (`5125552198`) and Carlos Reyes (`7375552184`). Call the desk and give Jane's number. It should offer to update her record instead of creating a second one.

```powershell
python -m pytest
```

Fourteen tests cover the API envelope, validation, soft-delete, a full spoken registration, a one-sentence registration, a spelled correction, a duplicate phone, Spanish, and the Vapi tool webhook.

## What I need from you

Nothing, to review the desk, the API, and the tests.

I do **not** need your passwords, and I should not receive API keys in chat or in git. If you want a live U.S. number later, put the keys in a local `.env` file (copy `.env.example`). That file is gitignored.

| Secret | Required for the review? | Where it goes | What it unlocks |
|---|---|---|---|
| None | The local demo works without one | — | Call desk, registry, API, tests |
| `GROQ_API_KEY` | Optional | `.env` | The local desk rephrases its lines with Llama. The phone path does not need this if Vapi runs the model. |
| `OPENAI_API_KEY` | Optional, paid | `.env` | Same rephrasing, used only when Groq is empty. |
| `PUBLIC_BASE_URL` | Only for a real phone call | `.env` and the Vapi assistant | The https address Vapi calls, for example your ngrok URL. |
| `VAPI_API_KEY` | Only if you want the assistant created from code | Vapi dashboard, or `.env` if we script it | Buying a number and saving the assistant. The webhook itself does not check this key. |

Do not commit `.env`. Do not paste a private key into GitHub, email, or this chat.

## Free accounts, in the order to open them

There is no reputable U.S. phone number that stays public and free forever. The path below keeps the cash outlay at zero for your own testing, and uses starter credit for the one number a reviewer would dial. Check each pricing page the day you sign up. Free tiers change.

### 1. Groq — free language model

- Site: https://console.groq.com
- Sign up with the same email you use for GitHub.
- Create an API key. No card has usually been required. The free tier is rate-limited.
- Put it in `.env` as `GROQ_API_KEY=` if you want the **browser desk** to sound less scripted.
- Model already set: `llama-3.3-70b-versatile`.
- Restart uvicorn after you save `.env`. `/health` should say `"voice_mode": "groq"`.

You can skip Groq entirely. The desk already speaks clear scripted lines, and the tests run with the model turned off.

### 2. Vapi — the phone agent

- Site: https://dashboard.vapi.ai
- Sign up. This is the fastest way to get a real call, which is what the review asks for. Vapi has historically given starter credit on a new account. Confirm the amount on their billing page.
- You do **not** have to build speech-to-text yourself.

In the dashboard:

1. Import `vapi/assistant.json`, or create an assistant and paste the system prompt from `app/voice/prompt.py` (`SYSTEM_PROMPT`).
2. Set the server URL to `https://YOUR-PUBLIC-HOST/voice/vapi`.
3. Under the model, either leave Vapi's included model (it spends Vapi credit) or point a custom OpenAI-compatible model at Groq:
   - Base URL `https://api.groq.com/openai/v1`
   - Model `llama-3.3-70b-versatile`
   - API key: the Groq key, stored in Vapi, not in this repo
4. Phone Numbers → buy one U.S. local number → attach this assistant.

A U.S. number is usually about a couple of dollars a month, plus a few cents a minute. Starter credit has been enough to cover a short hiring review. Web calls inside the Vapi dashboard are the free way to hear the agent before you buy the number.

The tools the assistant calls are `lookup_patient`, `create_patient`, `update_patient`, `list_appointment_slots`, and `book_appointment`. Our API validates every field. If the model sends a bad date, the tool result tells it to ask again, and nothing is saved.

### 3. ngrok — a public https address while your laptop is on

- Site: https://dashboard.ngrok.com/signup
- Free account. Install from https://ngrok.com/download
- `ngrok config add-authtoken YOUR_TOKEN`
- In a second terminal, with uvicorn already on port 8000: `ngrok http 8000`
- Copy the `https://….ngrok-free.app` URL into Vapi as the server URL, and into `.env` as `PUBLIC_BASE_URL`.

The free URL changes when ngrok restarts. The laptop has to stay awake while someone might call. That is the right tradeoff for a first demo and a bad one for a review scheduled while you are away.

### 4. Railway — only if the laptop cannot stay on

- Site: https://railway.com
- Trial credit. A card is sometimes required even on the trial.
- Deploy this repo as a Python service: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Put the Railway https URL in Vapi.

Render's free web services sleep. A reviewer who calls while the service is cold can hit silence. Prefer Railway or a machine you leave on.

### What not to use for the reviewer's call

**Twilio trial** (https://www.twilio.com/try-twilio) gives a number and trial credit, but that number only accepts calls from phone numbers you have verified in the Twilio console. A reviewer calling from their own phone will be rejected. Use Twilio only after you upgrade, or as the carrier behind Vapi once the account can receive calls from anyone.

**Google Voice, TextNow, and similar apps** do not give you a webhook when someone speaks. They are not a fit.

**Retell** (https://www.retellai.com) is a reasonable second choice if Vapi's signup is blocked. Same shape: assistant, tools, a U.S. number paid from trial credit. You would point its tool URL at `POST /voice/vapi` only if the payload matches; otherwise add a thin adapter. Vapi is the one this repo is wired for.

**Bland.ai** can place and receive calls, with less control over the tool contract. Not the first choice here.

## Architecture

```
Caller
  │  browser desk  or  U.S. number (Vapi)
  ▼
Conversation
  │  local script (always on)          Vapi model + SYSTEM_PROMPT
  │  optional Groq rephrase            tools POST /voice/vapi
  ▼
Patient service  ── the only writer ──►  SQLite (harbor.db)
  ▲
REST  /patients  /appointments  /calls
  ▲
Registry page
```

Telephony, the wording of the call, and the database are separate.

- `app/voice/extract.py` pulls names, dates, sex, phones, addresses, insurance, and a yes/no out of a sentence. It accepts information in any order.
- `app/voice/agent.py` decides the next step: keep collecting, offer optional fields, read the record back, recognize a duplicate phone, save, then offer a visit. It will not say the record was saved if the write failed.
- `app/voice/prompt.py` holds the scripted lines and the system prompt for the phone model. The prompt is commented at the top of that file.
- `app/voice/vapi.py` accepts Vapi tool-call payloads and end-of-call reports.
- `app/services/patients.py` is the only place a patient row is inserted or changed. The voice path and `POST /patients` both use it.
- `app/validation.py` enforces the field rules on the server. The voice agent is not trusted to be right.
- SQLite with WAL. The file survives a restart. A partial unique index lets a phone number be used again after a soft-delete, and blocks two active patients from sharing one.

A dropped browser call can resume. If you pass `caller_phone` when opening a session, an in-progress call from that number in the last two hours is continued. Older ones are marked `dropped`.

## What the caller hears

1. Greeting, then first and last name.
2. Date of birth, sex, phone, street, city, state, ZIP. If they say several of these in one sentence, the desk keeps them and only asks for what is missing.
3. One offer for insurance, email, apartment, emergency contact, or language. "No thanks" skips them.
4. A read-back of every collected field. "Yes" saves. A correction such as "my last name is spelled D-A-V-I-S" updates that field and reads it back again. Nothing is written before the yes.
5. If that phone already belongs to an active patient: "It looks like we already have a record for Jane Adler. Want me to update it instead?"
6. "You're all set, Priya." Then two upcoming weekday visit times with Dr. Leena Shah. "Yes" books the first. "No" ends the call.
7. "Start over" clears the card. "Hablo español" switches the rest of the call to Spanish and stores preferred language as Spanish.

Invalid data is asked again for that field only. A future birthday, a 3-digit phone, or a bad ZIP never reaches the table.

## Data model

`patients`

| Column | Rule |
|---|---|
| `patient_id` | UUID, generated |
| `first_name`, `last_name` | 1–50 letters, spaces, hyphens, apostrophes. Required. |
| `date_of_birth` | Real date, not in the future, year 1900 or later. API returns `MM/DD/YYYY`. |
| `sex` | Male, Female, Other, Decline to Answer |
| `phone_number` | 10-digit NANP, stored as digits. Area code and exchange cannot start with 0 or 1. |
| `email` | Optional |
| `address_line_1` | Required. `address_line_2` optional. |
| `city` | Required, up to 100 characters |
| `state` | 50 states plus DC. Full name or abbreviation. Stored as two letters. |
| `zip_code` | 5 digits or ZIP+4 |
| `insurance_provider`, `insurance_member_id` | Optional |
| `preferred_language` | Defaults to English |
| `emergency_contact_name`, `emergency_contact_phone` | Optional. Phone uses the same 10-digit rule. |
| `created_at`, `updated_at` | UTC |
| `deleted_at` | Set by `DELETE`. The row stays. |

`call_logs` stores the transcript, the phase, and the payload that was saved.

`appointments` stores a booked demo slot. Slots are the next weekday mornings (9:00) and afternoons (2:00) in `America/New_York`. They are not a real scheduling calendar.

## API

Every JSON body is `{ "data": ..., "error": null }` or `{ "data": null, "error": { "code", "message", "fields?" } }`.

| Method | Path | Result |
|---|---|---|
| `GET` | `/patients?last_name=&date_of_birth=&phone_number=` | `{ "data": { "patients": [...] } }` Active rows only. |
| `GET` | `/patients/{id}` | One patient, or 404. |
| `POST` | `/patients` | 201 and the created row. |
| `PUT` | `/patients/{id}` | Partial update. Unknown fields are rejected. |
| `DELETE` | `/patients/{id}` | Sets `deleted_at`. 200 with the row. |
| `GET` | `/appointments?patient_id=` | Booked visits. |
| `GET` | `/calls` | Recent transcripts. |
| `POST` | `/voice/sessions` | Opens a desk call. Optional `caller_phone`. |
| `POST` | `/voice/sessions/{id}/turns` | `{ "text": "..." }` |
| `POST` | `/voice/vapi` | Vapi tool calls and end-of-call reports. Always speaks through the tool result, not through a 500. |
| `GET` | `/health` | `voice_mode` is `script`, `groq`, or `openai`. |

Status codes used on purpose: 200, 201, 400 (body is not a JSON object), 404, 422 (field rules or a duplicate active phone), 500 (unexpected).

Example:

```powershell
curl http://127.0.0.1:8000/patients -Method POST -ContentType "application/json" -Body '{"first_name":"Priya","last_name":"Shah","date_of_birth":"07/15/1988","sex":"Female","phone_number":"512-555-2199","address_line_1":"88 Congress Avenue","city":"Austin","state":"Texas","zip_code":"78701"}'
```

## Environment

See `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./harbor.db` | Any SQLAlchemy URL. SQLite is the intended demo. |
| `SEED` | `true` | Insert Jane and Carlos when the table is empty. |
| `LLM_ENABLED` | `true` | Tests force this off so they never call the network. |
| `GROQ_API_KEY` | empty | Free rephrase for the local desk. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | |
| `OPENAI_API_KEY` | empty | Used only if Groq is empty. |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | Shown on `/voice/vapi/assistant` so you can copy it into Vapi. |

## Why these choices

- **SQLite instead of Postgres.** One file, no account, survives restarts. The service layer is ordinary SQLAlchemy, so Postgres is a URL change, not a rewrite. A partial unique index is SQLite-specific; on Postgres the same idea is a partial unique index in a migration.
- **A scripted desk plus a Vapi model, not a from-scratch speech stack.** The review is about wiring a call to a database. Vapi already does telephony, transcription, and voice. The local desk exists so the behavior can be tested with no vendor and no money.
- **The model is not allowed to write SQL.** It can only call tools. Invalid tools get a sentence back and a 200, so the caller hears an apology instead of silence.
- **Soft-delete.** A deleted patient disappears from the list and can no longer be fetched, and the phone number can be registered again.

## Limits

- Territories such as Puerto Rico are not accepted as `state`.
- The local parser is strong on the phrases in the tests and weaker on messy addresses ("the blue house behind the school"). The phone model covers more of that, and the server still rejects a value that does not match the field rules.
- "Mary Ann Smith" is stored as first name Mary and last name Ann Smith. "First name Mary Ann, last name Smith" is handled.
- Appointment times are generated. They are not checked against a real provider calendar, and two callers can book the same slot.
- The Vapi webhook does not verify a Vapi signature. Add that before any public deployment that is up for longer than the review.
- ngrok's free URL and a sleeping laptop will make a scheduled review fail even when the code is fine. Put the host somewhere that stays up the day they plan to call.
- No authentication on the API. That is acceptable for a private demo and not acceptable on a long-lived public URL. Do not type real patient data into it.
- Spanish on the local desk is the script in `LINES["es"]`. The Vapi prompt also tells the phone model to switch. Medical nuance in Spanish is not reviewed by a clinician.

## If the number is not ready in time

Document the blocker in the submission note: which vendor you opened, what the billing page said, and the local URL or ngrok URL plus the call desk. A working local registration still saves, lists, updates, and soft-deletes. The vendor outage is not the same as a broken save path.

## What I would do next

1. Buy the Vapi number on starter credit and place one test call from a second phone.
2. Verify the Vapi webhook signature.
3. Move `harbor.db` to Supabase or Railway Postgres if more than one instance will run.
4. Add a reserved ngrok domain, or leave Railway running, for the day of the review.
5. Rate-limit `POST /patients` and `POST /voice/vapi` if the URL stays public.

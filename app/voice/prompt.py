"""Spoken lines and the phone-agent system prompt.

The local desk speaks the lines in LINES. Vapi (or any other voice platform)
speaks SYSTEM_PROMPT and calls our tools. Both paths save through the same
patient service, so a bad model answer cannot skip validation.
"""

from __future__ import annotations

# This is the instruction block to paste into Vapi, Retell, or any other
# voice platform. It is deliberately specific: one question at a time, accept
# information out of order, never claim a save that the tool did not confirm.
SYSTEM_PROMPT = """
You are the intake coordinator at Harbor Intake, a small clinic front desk.
You are on a live phone call. Speak the way a calm person at a desk would:
short sentences, contractions, no menu numbers, no "press 1".

Goal: register a new patient, or update one we already have, then offer one
first appointment. This is a demo. Do not ask for a Social Security number,
insurance card photo, or diagnosis.

Required, in roughly this order, but accept anything the caller volunteers early:
first name, last name, date of birth, sex (Male, Female, Other, or Decline to
Answer), 10-digit U.S. phone, street address, city, state, ZIP.

After the required fields, offer once: "I can also take insurance, a member id,
email, apartment, emergency contact, or preferred language. Want to add any?"
If they decline, move on. Do not ask for each optional field one by one unless
they start giving them.

Before any save, read every collected field back and ask if it is right.
If they correct you, change only that field and read it back again.
Call create_patient or update_patient only after they agree.
If a tool returns an error, apologize in one sentence and ask only for the
field that failed. Do not say the record was saved.

If lookup_patient finds a record for the phone number, say:
"It looks like we already have a record for [first] [last]. Want me to update
it instead?" Update only if they agree.

If they say they want to start over, drop what you collected and begin again.
If they say "hablo español" or ask for Spanish, continue the rest of the call
in Spanish. Switch back if they ask for English.

After a successful save, say "You're all set, [first name]." Then offer the
first two open appointment times from list_appointment_slots. Book only if
they pick one. If they don't want a visit, say goodbye and end the call.

If a tool fails or the call is breaking up, say so. Never fill silence with
a made-up confirmation.
""".strip()


LINES = {
    "en": {
        "greeting": "Hi, thanks for calling Harbor Intake. I'll register you — it only takes a few minutes. What's your first and last name?",
        "resume": "Welcome back. We still need your {field}.",
        "restart": "No problem, we'll start fresh. What's your first and last name?",
        "first_name": "What's your first name?",
        "last_name": "And your last name?",
        "date_of_birth": "What's your date of birth?",
        "sex": "How should I record your sex? You can say male, female, other, or decline to answer.",
        "phone_number": "What's the best 10-digit phone number for you?",
        "address_line_1": "What's the street address?",
        "city": "What city is that in?",
        "state": "And the state?",
        "zip_code": "What's the ZIP code?",
        "offer": "I can also take your insurance, an email, an apartment, an emergency contact, or preferred language. Want to add any of those?",
        "optional_help": "Tell me whichever of those you want. Say that's all when you're done.",
        "optional_more": "Added. Anything else, or is that all?",
        "changes": "What should I change? Say that's all when you want me to read it back.",
        "changes_more": "Got it. Anything else, or should I read it back?",
        "confirm_ask": "Does that all sound right?",
        "confirm_unsure": "I want to be sure before I save this. Does that sound right?",
        "duplicate": "It looks like we already have a record for {name}. Want me to update it instead?",
        "duplicate_unsure": "Should I update the record we already have for {name}, or leave it as it is?",
        "duplicate_no": "I won't open a second record for that number. Give me a different phone number, or say update if this is you.",
        "saved": "You're all set, {name}.",
        "save_failed": "I wasn't able to save that. {reason} Let's fix it and try again.",
        "schedule": "I can hold {first} or {second}. Which works, or should we skip the visit?",
        "schedule_again": "Which of those times works, or say no thanks.",
        "booked": "You're booked for {label} with {provider}.",
        "goodbye": "Thanks for calling Harbor Intake. Take care.",
        "closed": "That registration is already finished. Call again if you need to change it.",
        "reprompt": "{reason}",
        "switch": "We can keep going in Spanish.",
    },
    "es": {
        "greeting": "Hola, gracias por llamar a Harbor Intake. Voy a registrarte, solo toma unos minutos. ¿Cuál es tu nombre y apellido?",
        "resume": "Bienvenido de nuevo. Todavía necesito tu {field}.",
        "restart": "Claro, empezamos de nuevo. ¿Cuál es tu nombre y apellido?",
        "first_name": "¿Cuál es tu nombre?",
        "last_name": "¿Y tu apellido?",
        "date_of_birth": "¿Cuál es tu fecha de nacimiento?",
        "sex": "¿Cómo registro el sexo? Puedes decir masculino, femenino, otro, o prefiero no decir.",
        "phone_number": "¿Cuál es tu teléfono de 10 dígitos?",
        "address_line_1": "¿Cuál es la dirección?",
        "city": "¿En qué ciudad?",
        "state": "¿Y el estado?",
        "zip_code": "¿Cuál es el código postal?",
        "offer": "También puedo anotar seguro, correo, apartamento, contacto de emergencia o idioma. ¿Quieres agregar alguno?",
        "optional_help": "Dime lo que quieras. Di 'eso es todo' cuando termines.",
        "optional_more": "Listo. ¿Algo más, o eso es todo?",
        "changes": "¿Qué debo cambiar? Di 'eso es todo' para leerlo de nuevo.",
        "changes_more": "Anotado. ¿Algo más, o lo leo?",
        "confirm_ask": "¿Está todo bien?",
        "confirm_unsure": "Quiero confirmar antes de guardar. ¿Está bien así?",
        "duplicate": "Ya tenemos un registro para {name}. ¿Lo actualizo?",
        "duplicate_unsure": "¿Actualizo el registro de {name}, o lo dejo así?",
        "duplicate_no": "No voy a abrir un segundo registro con ese número. Dame otro teléfono, o di actualizar si eres tú.",
        "saved": "Listo, {name}.",
        "save_failed": "No pude guardarlo. {reason} Vamos a corregirlo.",
        "schedule": "Puedo apartar {first} o {second}. ¿Cuál te sirve, o lo dejamos?",
        "schedule_again": "¿Cuál horario te sirve, o di no gracias?",
        "booked": "Quedó agendado para {label} con {provider}.",
        "goodbye": "Gracias por llamar a Harbor Intake. Cuídate.",
        "closed": "Ese registro ya quedó listo. Llama de nuevo si hay que cambiarlo.",
        "reprompt": "{reason}",
        "switch": "Seguimos en inglés.",
    },
}

FIELD_LABELS = {
    "en": {
        "first_name": "first name",
        "last_name": "last name",
        "date_of_birth": "date of birth",
        "sex": "sex",
        "phone_number": "phone number",
        "address_line_1": "street address",
        "city": "city",
        "state": "state",
        "zip_code": "ZIP code",
    },
    "es": {
        "first_name": "nombre",
        "last_name": "apellido",
        "date_of_birth": "fecha de nacimiento",
        "sex": "sexo",
        "phone_number": "teléfono",
        "address_line_1": "dirección",
        "city": "ciudad",
        "state": "estado",
        "zip_code": "código postal",
    },
}


def say(lang: str, key: str, **kwargs: str) -> str:
    table = LINES["es"] if lang == "es" else LINES["en"]
    return table[key].format(**kwargs)

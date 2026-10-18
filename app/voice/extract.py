from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.validation import (
    MONTHS,
    STATE_ABBRS,
    STATE_NAMES,
    canonical_sex,
    normalize_field,
    normalize_phone,
    parse_dob,
)

PHONE_RE = re.compile(r"(?:\+?1[\s\-.]?)?\(?([2-9]\d{2})\)?[\s\-.]?([2-9]\d{2})[\s\-.]?(\d{4})")
EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
STREET_RE = re.compile(
    r"\b(\d{1,6}\s+(?:[A-Za-z0-9.'-]+\s){0,5}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way|Court|Ct|Place|Pl|Parkway|Pkwy)\.?)\b",
    re.IGNORECASE,
)
ZIP_RE = re.compile(r"\b(\d{5})(?:-(\d{4}))?\b")
UNIT_RE = re.compile(r"\b(?:apartment|apt|suite|ste|unit)\s*#?\s*([A-Za-z0-9\-]+)", re.IGNORECASE)

YES = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "correct",
    "that's right",
    "that is right",
    "thats right",
    "confirm",
    "confirmed",
    "sounds good",
    "all good",
    "save it",
    "save that",
    "that's correct",
    "that is correct",
    "thats correct",
    "yes please",
    "go ahead",
    "si",
    "sí",
    "correcto",
    "esta bien",
    "está bien",
}
NO = {
    "no",
    "nope",
    "nah",
    "wrong",
    "incorrect",
    "that's wrong",
    "that is wrong",
    "no thanks",
    "no thank you",
    "no gracias",
    "skip",
    "none",
    "not now",
    "not correct",
}
SEX_WORDS = {"male", "female", "man", "woman", "other", "calling", "here"}


@dataclass
class Parse:
    fields: dict = field(default_factory=dict)
    invalid: dict = field(default_factory=dict)
    yes: bool = False
    no: bool = False
    done: bool = False
    start_over: bool = False
    lang: str | None = None


def parse_utterance(text: str, pending: str | None = None) -> Parse:
    raw = (text or "").strip()
    result = Parse()
    if not raw:
        return result
    lower = raw.lower()
    result.start_over = bool(re.search(r"\b(start over|start again|begin again|scratch that|from the top)\b", lower))
    if re.search(r"hablo espa|en espa|spanish please|speak spanish|espa[nñ]ol", lower):
        result.lang = "es"
        result.fields["preferred_language"] = "Spanish"
    elif re.search(r"\b(in english|speak english|english please)\b", lower):
        result.lang = "en"
        result.fields["preferred_language"] = "English"
    result.done = bool(
        re.search(r"\b(that'?s all|that is all|nothing else|nada m[aá]s|eso es todo|that'?s it|that is it)\b", lower)
    )

    _take_spelled_name(raw, result)
    _take_labeled_names(raw, result)
    _take_full_name(raw, result)
    _take_dob(raw, result)
    _take_sex(raw, result)
    _take_email(raw, result)
    phone_spans = _take_phones(raw, pending, result)
    _take_zip(raw, phone_spans, result)
    _take_state_city_street(raw, result)
    _take_unit(raw, result)
    _take_insurance(raw, result)
    _take_emergency_name(raw, result)
    if not result.lang:
        _take_pending_bare(raw, pending, result)
    _validate(result)

    bare = _bare(raw)
    if not result.fields and not result.invalid:
        result.yes = bare in YES
        result.no = bare in NO
    return result


def _bare(text: str) -> str:
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[.!?]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def spelled_word(chunk: str) -> str | None:
    parts = re.split(r"[\s\-]+", chunk.strip(" .,"))
    if len(parts) >= 3 and all(len(part) == 1 and part.isalpha() for part in parts):
        return "".join(parts).capitalize()
    return None


def _take_spelled_name(raw: str, result: Parse) -> None:
    match = re.search(r"spelled\s+((?:[A-Za-z][\s\-]+){2,}[A-Za-z])", raw, re.IGNORECASE)
    word = spelled_word(match.group(1)) if match else None
    if word and re.search(r"first name", raw, re.IGNORECASE):
        result.fields["first_name"] = word
    elif word:
        result.fields["last_name"] = word


def _take_labeled_names(raw: str, result: Parse) -> None:
    first = re.search(
        r"\bfirst name(?: is)?\s+([A-Za-z][A-Za-z'\- ]{0,40}?)(?=\s+last name\b|,|\.|$)",
        raw,
        re.IGNORECASE,
    )
    last = re.search(
        r"\blast name(?: is)?\s+([A-Za-z][A-Za-z'\- ]{0,40}?)(?=,|\.|$|\s+and\b|\s+date\b)",
        raw,
        re.IGNORECASE,
    )
    if first and "first_name" not in result.fields and "spelled" not in first.group(1).lower():
        result.fields["first_name"] = first.group(1).strip()
    if last and "last_name" not in result.fields and "spelled" not in last.group(1).lower():
        result.fields["last_name"] = last.group(1).strip()


def _take_full_name(raw: str, result: Parse) -> None:
    if "first_name" in result.fields or "last_name" in result.fields:
        return
    match = re.search(
        r"\b(?:my name is|i am|i'm|this is)\s+"
        r"([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,3}?)"
        r"(?=\s*(?:,|\.| and\b| born\b| date\b| dob\b| phone\b| my\b|$))",
        raw,
        re.IGNORECASE,
    )
    if not match:
        return
    words = [word for word in match.group(1).split() if word.lower() not in SEX_WORDS]
    if not words:
        return
    result.fields["first_name"] = words[0]
    if len(words) > 1:
        result.fields["last_name"] = " ".join(words[1:])


def _take_dob(raw: str, result: Parse) -> None:
    numeric = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", raw)
    named = re.search(
        r"\b([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?\,?\s+\d{4})\b",
        raw,
        re.IGNORECASE,
    )
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw)
    chunk = None
    if numeric:
        chunk = numeric.group(1)
    elif iso:
        chunk = iso.group(1)
    elif named and named.group(1).split()[0].lower() in MONTHS:
        chunk = named.group(1)
    if not chunk:
        return
    parsed, err = parse_dob(chunk)
    if err or parsed is None:
        # A numeric date that is not a real calendar date should be rejected, not ignored.
        if numeric or iso or (named and named.group(1).split()[0].lower() in MONTHS):
            result.invalid["date_of_birth"] = err or "That isn't a real calendar date."
        return
    result.fields["date_of_birth"] = parsed.isoformat()


def _take_sex(raw: str, result: Parse) -> None:
    without_email = EMAIL_RE.sub(" ", raw)
    bare = _bare(without_email)
    if bare in {"m", "f", "male", "female", "man", "woman", "other", "decline", "decline to answer", "nonbinary", "non-binary"}:
        sex = canonical_sex(bare)
        if sex:
            result.fields["sex"] = sex
            return
    for phrase in (
        "decline to answer",
        "prefer not to say",
        "rather not say",
        "non-binary",
        "nonbinary",
        "prefiero no decir",
        "femenino",
        "masculino",
        "female",
        "woman",
        "male",
        "man",
        "mujer",
        "hombre",
        "other",
        "otro",
    ):
        if re.search(rf"\b{re.escape(phrase)}\b", without_email, re.IGNORECASE):
            sex = canonical_sex(phrase)
            if sex:
                result.fields["sex"] = sex
            return


def _take_email(raw: str, result: Parse) -> None:
    match = EMAIL_RE.search(raw)
    if match:
        result.fields["email"] = match.group(1)


def _take_phones(raw: str, pending: str | None, result: Parse) -> list[tuple[int, int]]:
    matches = list(PHONE_RE.finditer(raw))
    spans = [(match.start(), match.end()) for match in matches]
    numbers = ["".join(match.groups()) for match in matches]
    if len(numbers) >= 2:
        result.fields["phone_number"] = numbers[0]
        result.fields["emergency_contact_phone"] = numbers[1]
    elif len(numbers) == 1:
        key = "emergency_contact_phone" if pending == "emergency_contact_phone" or re.search(r"emergency", raw, re.I) else "phone_number"
        result.fields[key] = numbers[0]
    elif pending in ("phone_number", "emergency_contact_phone") or re.search(r"\b(phone|number)\b", raw, re.I):
        if re.search(r"\d", raw):
            key = "emergency_contact_phone" if pending == "emergency_contact_phone" else "phone_number"
            probe = normalize_phone(raw)
            if probe is None:
                result.invalid[key] = "I need all 10 digits of a U.S. number, like 512-555-2198."
    return spans


def _take_zip(raw: str, phone_spans: list[tuple[int, int]], result: Parse) -> None:
    for match in ZIP_RE.finditer(raw):
        start_at = match.start()
        end_at = match.end()
        if any(not (end_at <= span_start or start_at >= span_end) for span_start, span_end in phone_spans):
            continue
        head = raw[start_at - 1] if start_at else ""
        tail = raw[end_at] if end_at < len(raw) else ""
        if head.isdigit() or tail.isdigit():
            continue
        zip_code = match.group(1) if not match.group(2) else f"{match.group(1)}-{match.group(2)}"
        result.fields["zip_code"] = zip_code
        return


def _find_state(raw: str) -> tuple[str, tuple[int, int]] | None:
    lower = raw.lower()
    names = sorted(STATE_NAMES, key=len, reverse=True)
    for name in names:
        match = re.search(rf"\b{re.escape(name)}\b", lower)
        if match:
            return STATE_NAMES[name], match.span()
    if re.fullmatch(r"[A-Za-z]{2}", raw.strip()) and raw.strip().upper() in STATE_ABBRS:
        return raw.strip().upper(), (0, len(raw.strip()))
    for match in re.finditer(r"\b([A-Z]{2})\b", raw):
        if match.group(1) in STATE_ABBRS:
            return match.group(1), match.span()
    return None


def _take_state_city_street(raw: str, result: Parse) -> None:
    street = STREET_RE.search(raw)
    if street:
        result.fields["address_line_1"] = re.sub(r"\s+", " ", street.group(1)).rstrip(".")
    found = _find_state(raw)
    if found:
        abbr, span = found
        result.fields["state"] = abbr
        head = raw[: span[0]]
        if street:
            idx = head.lower().rfind(street.group(1).lower())
            if idx >= 0:
                head = head[idx + len(street.group(1)) :]
        head = head.strip(" ,.")
        if "," in head:
            head = head.split(",")[-1].strip()
        head = re.sub(r"^(?:in|at|city of)\s+", "", head, flags=re.IGNORECASE).strip(" ,.")
        if head and not normalize_phone(head):
            result.fields["city"] = head


def _take_unit(raw: str, result: Parse) -> None:
    match = UNIT_RE.search(raw)
    if match:
        label = match.group(0)
        result.fields["address_line_2"] = label.strip().title().replace("Apt", "Apt")


def _take_insurance(raw: str, result: Parse) -> None:
    member = re.search(r"\b(?:member|subscriber)(?:\s+id|\s+number)?(?:\s+is)?\s+([A-Za-z0-9\-]+)", raw, re.I)
    if member:
        result.fields["insurance_member_id"] = member.group(1)
    provider = re.search(
        r"\binsurance(?: provider)?(?:\s+is|\s+with)?\s+([A-Za-z0-9][A-Za-z0-9 &'.,\-]{1,60}?)(?=\s+member\b|,|\.|$)",
        raw,
        re.IGNORECASE,
    )
    if provider:
        result.fields["insurance_provider"] = provider.group(1).strip()


def _take_emergency_name(raw: str, result: Parse) -> None:
    match = re.search(
        r"\bemergency contact(?:\s+is|\s+named)?\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,3})",
        raw,
        re.IGNORECASE,
    )
    if match:
        result.fields["emergency_contact_name"] = match.group(1).strip()


def _take_pending_bare(raw: str, pending: str | None, result: Parse) -> None:
    if not pending or pending in result.fields or pending in result.invalid:
        return
    text = raw.strip().rstrip(".")
    if pending in ("first_name", "last_name"):
        spelled = spelled_word(text)
        if spelled:
            result.fields[pending] = spelled
            return
        if re.fullmatch(r"[A-Za-z][A-Za-z'\- ]{0,49}", text) and text.lower() not in YES | NO | SEX_WORDS:
            words = text.split()
            if pending == "first_name" and len(words) >= 2 and "last_name" not in result.fields:
                result.fields["first_name"] = words[0]
                result.fields["last_name"] = " ".join(words[1:])
            else:
                result.fields[pending] = text
        return
    if pending == "date_of_birth":
        parsed, err = parse_dob(text)
        if parsed:
            result.fields["date_of_birth"] = parsed.isoformat()
        else:
            result.invalid["date_of_birth"] = err or "Use a real past date, like March 4, 1990."
        return
    if pending == "sex":
        sex = canonical_sex(text)
        if sex:
            result.fields["sex"] = sex
        else:
            result.invalid["sex"] = "Say male, female, other, or decline to answer."
        return
    if pending == "address_line_1" and "address_line_1" not in result.fields:
        if "date_of_birth" not in result.fields and "phone_number" not in result.fields and re.search(r"\d", text):
            result.fields["address_line_1"] = re.sub(r"\s+", " ", text)
        return
    if pending == "city" and re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{0,80}", text):
        if text.lower() not in STATE_NAMES:
            result.fields["city"] = text
        return
    if pending == "state":
        result.invalid["state"] = "Tell me the state, like Texas or TX."
        return
    if pending == "zip_code":
        result.invalid["zip_code"] = "I need a 5-digit ZIP code."
        return
    if pending == "email":
        result.invalid["email"] = "That email doesn't look valid."
        return
    if pending == "insurance_provider" and re.fullmatch(r"[A-Za-z0-9 &'.,\-]{2,80}", text):
        result.fields["insurance_provider"] = text
        return
    if pending == "preferred_language" and re.fullmatch(r"[A-Za-z \-]{2,40}", text):
        result.fields["preferred_language"] = text


def _validate(result: Parse) -> None:
    checked = {}
    for key, value in list(result.fields.items()):
        if key == "date_of_birth":
            parsed, err = parse_dob(value)
            if err or parsed is None:
                result.invalid[key] = err or "That date doesn't work."
                continue
            checked[key] = parsed.isoformat()
            continue
        norm, err = normalize_field(key, value)
        if err:
            result.invalid[key] = err
        else:
            checked[key] = norm if key != "date_of_birth" else value
    result.fields = checked

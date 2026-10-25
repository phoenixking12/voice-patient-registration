from __future__ import annotations

import re
from datetime import date, datetime

NAME_RE = re.compile(r"^[A-Za-z](?:[A-Za-z]|[ '\-](?=[A-Za-z])){0,49}$")
CITY_RE = re.compile(r"^[A-Za-z](?:[A-Za-z]|[ .'\-](?=[A-Za-z])){0,99}$")
ADDRESS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,'#/\-]{0,119}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
MEMBER_RE = re.compile(r"^[A-Za-z0-9\-]{1,40}$")
LANGUAGE_RE = re.compile(r"^[A-Za-z][A-Za-z \-]{0,39}$")
INSURANCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &'.,\-]{0,79}$")

SEX_VALUES = ("Male", "Female", "Other", "Decline to Answer")

# Full names are matched longest-first so "West Virginia" wins over "Virginia".
STATE_NAMES: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "washington dc": "DC",
    "washington d.c.": "DC",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}
STATE_ABBRS = set(STATE_NAMES.values())

REQUIRED_FIELDS = (
    "first_name",
    "last_name",
    "date_of_birth",
    "sex",
    "phone_number",
    "address_line_1",
    "city",
    "state",
    "zip_code",
)
OPTIONAL_FIELDS = (
    "email",
    "address_line_2",
    "insurance_provider",
    "insurance_member_id",
    "preferred_language",
    "emergency_contact_name",
    "emergency_contact_phone",
)
PATIENT_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


PHONE_HINT = "Use a country code, like +92 300 1234567, or a 10-digit U.S. number like 512-555-2198."
DATE_HINT = "Please use month/day/year, like 03/04/1990. March 4, 1990 works too."


def normalize_phone(value: str) -> str | None:
    raw = value or ""
    has_plus = "+" in raw
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
        has_plus = True
    if not digits:
        return None
    # A leading 1 on 11 digits is the U.S. country code.
    if len(digits) == 11 and digits.startswith("1"):
        national = digits[1:]
        if national[0] not in "01" and national[3] not in "01":
            return national
    if len(digits) == 10 and digits[0] not in "01" and digits[3] not in "01" and not has_plus:
        return digits
    # Any other country: keep the country code. Stored with a leading +.
    if 8 <= len(digits) <= 15 and digits[0] != "0":
        return "+" + digits
    return None


def parse_dob(value: date | datetime | str) -> tuple[date | None, str | None]:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        found = value
    else:
        text = str(value).strip()
        found = _parse_dob_text(text)
        if found is None:
            return None, DATE_HINT
    today = date.today()
    if found > today:
        return None, "That date is in the future. Tell me a date of birth that has already happened."
    if found.year < 1900:
        return None, "I need a date of birth in 1900 or later."
    return found, None


def _parse_dob_text(text: str) -> date | None:
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if numeric:
        first, second = int(numeric.group(1)), int(numeric.group(2))
        year = expand_year(int(numeric.group(3)))
        # 25/10/1990 cannot be month-first. The told format stays month/day/year when both are possible.
        if first > 12 and 1 <= second <= 12:
            return _safe_date(year, second, first)
        return _safe_date(year, first, second)
    day_first = re.fullmatch(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+)\,?\s+(\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if day_first:
        month = MONTHS.get(day_first.group(2).lower())
        if month:
            return _safe_date(int(day_first.group(3)), month, int(day_first.group(1)))
    named = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\,?\s+(\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if named:
        month = MONTHS.get(named.group(1).lower())
        if not month:
            return None
        return _safe_date(int(named.group(3)), month, int(named.group(2)))
    return None


def expand_year(year: int) -> int:
    if year >= 100:
        return year
    cutoff = date.today().year % 100
    return 2000 + year if year <= cutoff else 1900 + year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def normalize_state(value: str) -> str | None:
    text = (value or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", text) and text.upper() in STATE_ABBRS:
        return text.upper()
    return STATE_NAMES.get(re.sub(r"\s+", " ", text.lower()))


def normalize_field(key: str, value):  # noqa: ANN001
    if key in ("first_name", "last_name", "emergency_contact_name"):
        text = re.sub(r"\s+", " ", str(value).strip())
        if not NAME_RE.fullmatch(text):
            return None, "Use letters, spaces, hyphens, or apostrophes, up to 50 characters."
        return text, None
    if key == "date_of_birth":
        return parse_dob(value)
    if key == "sex":
        found = canonical_sex(str(value))
        if not found:
            return None, "Say Male, Female, Other, or Decline to Answer."
        return found, None
    if key in ("phone_number", "emergency_contact_phone"):
        phone = normalize_phone(str(value))
        if not phone:
            return None, PHONE_HINT
        return phone, None
    if key == "email":
        text = str(value).strip()
        if not EMAIL_RE.fullmatch(text) or len(text) > 254:
            return None, "That email doesn't look valid."
        return text, None
    if key in ("address_line_1", "address_line_2"):
        text = re.sub(r"\s+", " ", str(value).strip())
        if not ADDRESS_RE.fullmatch(text):
            return None, "Keep the address under 120 characters, without unusual symbols."
        return text, None
    if key == "city":
        text = re.sub(r"\s+", " ", str(value).strip())
        if not CITY_RE.fullmatch(text):
            return None, "Use a city name, up to 100 characters."
        return text, None
    if key == "state":
        state = normalize_state(str(value))
        if not state:
            return None, "Use a U.S. state, like Texas or TX."
        return state, None
    if key == "zip_code":
        text = str(value).strip()
        if not ZIP_RE.fullmatch(text):
            return None, "Use a 5-digit ZIP or ZIP+4, like 78701 or 78701-1234."
        return text, None
    if key == "insurance_provider":
        text = re.sub(r"\s+", " ", str(value).strip())
        if not INSURANCE_RE.fullmatch(text):
            return None, "Keep the insurance name under 80 characters."
        return text, None
    if key == "insurance_member_id":
        text = str(value).strip()
        if not MEMBER_RE.fullmatch(text):
            return None, "Use letters, numbers, or hyphens for the member id."
        return text, None
    if key == "preferred_language":
        text = re.sub(r"\s+", " ", str(value).strip())
        if not LANGUAGE_RE.fullmatch(text):
            return None, "Keep the language name under 40 letters."
        return text[:1].upper() + text[1:], None
    return None, "Unknown field."


def canonical_sex(value: str) -> str | None:
    text = value.strip().lower()
    table = {
        "male": "Male",
        "m": "Male",
        "man": "Male",
        "female": "Female",
        "f": "Female",
        "woman": "Female",
        "other": "Other",
        "nonbinary": "Other",
        "non-binary": "Other",
        "decline": "Decline to Answer",
        "decline to answer": "Decline to Answer",
        "prefer not to say": "Decline to Answer",
        "prefer not": "Decline to Answer",
        "rather not": "Decline to Answer",
        "rather not say": "Decline to Answer",
        "masculino": "Male",
        "hombre": "Male",
        "femenino": "Female",
        "mujer": "Female",
        "otro": "Other",
        "prefiero no decir": "Decline to Answer",
    }
    if text in table:
        return table[text]
    if value.strip() in SEX_VALUES:
        return value.strip()
    return None


def normalize_patient(data: dict, *, partial: bool) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    clean: dict = {}
    if not isinstance(data, dict):
        return {}, {"body": "Patient details have to be an object."}
    for key in data:
        if key not in PATIENT_FIELDS:
            errors[key] = "This field is not part of the patient record."
    if not partial:
        for key in REQUIRED_FIELDS:
            if data.get(key) in (None, ""):
                errors[key] = "This field is required."
    for key in PATIENT_FIELDS:
        if key not in data or key in errors and key not in PATIENT_FIELDS:
            continue
        if key not in data:
            continue
        value = data.get(key)
        if value in (None, ""):
            if key in REQUIRED_FIELDS:
                errors[key] = "This field is required."
            elif partial:
                clean[key] = None
            continue
        norm, err = normalize_field(key, value)
        if err:
            errors[key] = err
        else:
            clean[key] = norm
    if not partial and "preferred_language" not in clean and "preferred_language" not in errors:
        clean["preferred_language"] = "English"
    return clean, errors

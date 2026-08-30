"""One parser for Vietnamese money, replacing five that disagreed.

Before this module, `"1.500 trieu"` was 1.5 triệu to the inventory tool and 1.5 tỷ to the
document conflict detector — a thousandfold gap in the two places most likely to quote a
customer a number. `"3 t"` meant 3 tỷ to one and 3 đồng to the other, `"3 million"` was
understood by one and ignored by the other, and the northern spelling `tỉ` was recognised by
exactly one regex out of five. See tests/test_utils/test_vnd_characterization.py for the
recorded evidence.

Two profiles, because the divergence was not purely accidental:

`CONVERSATIONAL` reads what a person types into a chat box. It accepts the bare `t`
abbreviation as tỷ ("căn 3t") and treats a dot as a decimal point, because someone writing
"2.5 tỷ" means two and a half billion.

`DOCUMENT` reads price tables lifted out of PDFs. It accepts English unit names and explicit
đồng units, and reads a dot as a thousands separator where the grouping is unambiguous
("1.500.000 VND" is one and a half million, not one and a half). It deliberately does *not*
accept a bare `t`, which in a spreadsheet cell is far more likely to be "tầng" or "tấn".

Both return whole đồng: there is no such thing as a fractional đồng in a price list, and an
`int` avoids the float-comparison surprises the old `float`-returning parser produced.
"""

import re
from enum import Enum

from backend.utils.text import strip_diacritics

_BILLION = 1_000_000_000
_MILLION = 1_000_000


class Profile(Enum):
    """Which unit vocabulary to read the input with."""

    CONVERSATIONAL = "conversational"
    DOCUMENT = "document"


# Diacritics are stripped before lookup, so keys are unaccented. Note `tỷ` normalises to
# `ty` but `tỉ` normalises to `ti` — the two spellings do NOT collapse to one key, so both
# are listed. Getting this wrong is what left `tỉ` unrecognised in four of the five original
# call sites.
_CONVERSATIONAL_UNITS = {
    "ty": _BILLION,
    "ti": _BILLION,
    "t": _BILLION,
    "trieu": _MILLION,
    "tr": _MILLION,
}

_DOCUMENT_UNITS = {
    "ty": _BILLION,
    "ti": _BILLION,
    "billion": _BILLION,
    "trieu": _MILLION,
    "tr": _MILLION,
    "million": _MILLION,
    "vnd": 1,
    "dong": 1,
    "d": 1,
}

_UNITS: dict[Profile, dict[str, int]] = {
    Profile.CONVERSATIONAL: _CONVERSATIONAL_UNITS,
    Profile.DOCUMENT: _DOCUMENT_UNITS,
}

# Every spelling any caller may need to match, longest first so `trieu` wins over `tr` and
# the alternation never truncates a longer unit. Exported so the five regexes that used to
# hand-list their own subset share one vocabulary and cannot drift apart again.
UNIT_ALTERNATION = "|".join(
    sorted(
        {"tỷ", "tỉ", "ty", "ti", "t", "triệu", "trieu", "tr", "million", "billion", "vnd", "dong"},
        key=len,
        reverse=True,
    )
)

# "1.500.000" — two or more groups of three, which no decimal notation produces. A single
# group ("1.500") is deliberately excluded: it is ambiguous, and reading it as one thousand
# five hundred would turn "1.500 tỷ" into 1500 tỷ. One group stays a decimal, so "1.500 tỷ"
# is 1.5 tỷ under both profiles.
_GROUPED_THOUSANDS = re.compile(r"\d{1,3}(?:[.,]\d{3}){2,}")


def parse_vnd(number: str, unit: str | None, *, profile: Profile) -> int | None:
    """Convert a number and its unit to whole đồng, or None if the number is unreadable.

    Returns None rather than raising: every caller runs this inside a regex loop over
    free text, where one malformed match should skip that match rather than abort the
    scan. The old inventory parser raised ValueError on "1.500.000" and callers simply
    had no branch for it.
    """
    compact = (number or "").strip()
    if not compact:
        return None

    units = _UNITS[profile]
    key = strip_diacritics(unit or "").strip().lower()
    multiplier = units.get(key)

    # A grouped-thousands literal is only read as such under DOCUMENT: "1.500 tỷ" typed by a
    # person is 1.5 tỷ, while "1.500.000 VND" printed in a table is one and a half million.
    if profile is Profile.DOCUMENT and _GROUPED_THOUSANDS.fullmatch(compact):
        digits = re.sub(r"[.,]", "", compact)
        return int(digits) * (multiplier if multiplier is not None else 1)

    try:
        value = float(compact.replace(",", "."))
    except ValueError:
        return None

    return round(value * (multiplier if multiplier is not None else 1))

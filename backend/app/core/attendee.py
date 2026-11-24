"""Values shared by the pass-purchase form, the ID card studio and the desk.

Storage is compact on purpose: one small integer per answer instead of a string.
The API and the UI still speak readable names, so a new screen cannot invent a
third spelling. Unknown old strings are treated as "not answered" rather than
guessed at.
"""

from typing import Literal

Gender = Literal["male", "female"]
FoodPreference = Literal["veg", "non_veg"]

# The stored codes. 0 = male / veg, 1 = female / non-veg.
GENDER_CODES: dict[str, int] = {"male": 0, "female": 1}
FOOD_CODES: dict[str, int] = {"veg": 0, "non_veg": 1}

GENDER_NAMES: dict[int, str] = {code: name for name, code in GENDER_CODES.items()}
FOOD_NAMES: dict[int, str] = {code: name for name, code in FOOD_CODES.items()}

GENDER_LABELS = {"male": "Male", "female": "Female"}
FOOD_LABELS = {"veg": "Vegetarian", "non_veg": "Non-vegetarian"}


def encode_gender(value: str | int | None) -> int | None:
    """Name or already-encoded value to the stored code."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value if value in GENDER_NAMES else None
    return GENDER_CODES.get(str(value).strip().lower())


def encode_food(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value if value in FOOD_NAMES else None
    return FOOD_CODES.get(str(value).strip().lower())


def decode_gender(code: int | None) -> str | None:
    return GENDER_NAMES.get(code) if code is not None else None


def decode_food(code: int | None) -> str | None:
    return FOOD_NAMES.get(code) if code is not None else None


__all__ = [
    "FOOD_CODES",
    "FOOD_LABELS",
    "FOOD_NAMES",
    "GENDERS",
    "GENDER_CODES",
    "GENDER_LABELS",
    "GENDER_NAMES",
    "FOOD_PREFERENCES",
    "FoodPreference",
    "Gender",
    "decode_food",
    "decode_gender",
    "encode_food",
    "encode_gender",
]

GENDERS: tuple[str, ...] = tuple(GENDER_CODES)
FOOD_PREFERENCES: tuple[str, ...] = tuple(FOOD_CODES)

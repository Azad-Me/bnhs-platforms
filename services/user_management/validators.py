from __future__ import annotations


def clean_required_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("This field must not be blank.")
    return cleaned


def normalize_role_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Role key must be a string.")
    return value.strip().casefold()

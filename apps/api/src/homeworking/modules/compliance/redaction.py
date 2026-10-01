"""Heuristic removal of personal data from text before it is sent to an LLM (GDPR Art. 5/25)."""

from __future__ import annotations

import re

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[E-MAIL]"),
    (re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b"), "[IBAN]"),
    (re.compile(r"(?<!\w)(?:\+49|0049|0)[\s/-]?\d{2,5}[\s/-]?\d{3,}(?:[\s-]?\d+)*"), "[TELEFON]"),
    (
        re.compile(
            r"\b[A-ZÄÖÜ][\wäöüß-]*(?:straße|strasse|str\.|weg|allee|platz|gasse|ring|damm)"
            r"\s+\d+\s?[a-zA-Z]?\b"
        ),
        "[ADRESSE]",
    ),
    (
        re.compile(r"\b(?:Flurst(?:ück|ueck)|Flur)\s*(?:Nr\.?\s*)?[\d/]+", re.IGNORECASE),
        "[FLURSTÜCK]",
    ),
)


def redact(text: str) -> str:
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text

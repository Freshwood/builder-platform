"""Rule-based safety gate that runs before every agent turn.

Topics that must be handled by licensed professionals get a fixed referral instead of DIY
instructions. Rules are deliberately conservative; false positives only cost a referral.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SAFETY_RULES_VERSION = "2"


@dataclass(frozen=True)
class SafetyTopic:
    key: str
    pattern: re.Pattern[str]
    response: str


def _p(*alternatives: str) -> re.Pattern[str]:
    return re.compile("|".join(alternatives), re.IGNORECASE)


TOPICS: tuple[SafetyTopic, ...] = (
    SafetyTopic(
        key="electrical",
        pattern=_p(
            r"steckdose",
            r"sicherungskasten",
            r"unterverteilung",
            r"stromkreis",
            r"elektroinstallation",
            r"starkstrom",
            r"\b(230|400)\s?v(olt)?\b",
            r"\bfi[- ]?schalter",
            r"lichtschalter",
            r"(strom|elektro)leitung",
            r"kabel\s+(verlegen|anschlie)",
        ),
        response=(
            "Arbeiten an der festen Elektroinstallation (230/400 V) dürfen nur Elektrofachkräfte "
            "bzw. im Installateurverzeichnis eingetragene Betriebe ausführen. Dafür erstelle ich "
            "keine Bauanleitung. Ich kann dir aber helfen, das übrige Vorhaben zu planen und "
            "z. B. eine Leerrohr-Trasse für den Elektriker vorzusehen."
        ),
    ),
    SafetyTopic(
        key="gas_fire",
        pattern=_p(
            r"\bgas(leitung|therme|herd|anschluss|flasche\w* anschlie)",
            r"kamin",
            r"schornstein",
            r"feuerst(ä|ae)tte",
            r"ofen\s*(einbauen|anschlie|setzen)",
            r"abgasrohr",
        ),
        response=(
            "Gasanlagen, Feuerstätten und Abgasanlagen gehören in die Hand eines Fachbetriebs; "
            "Feuerstätten nimmt zudem der Bezirksschornsteinfeger ab. Dafür gebe ich keine "
            "Bauanleitung. Bei Planung, Materialauswahl für das Umfeld oder Fragen an den "
            "Fachbetrieb helfe ich gern."
        ),
    ),
    SafetyTopic(
        key="structural",
        pattern=_p(
            r"tragende\w*\s+wand",
            r"wanddurchbruch",
            r"deckendurchbruch",
            r"decke\s+(öffnen|durchbrechen|entfernen)",
            # Changes to an existing roof structure; planning a new house is allowed (ADR-0007).
            r"dachstuhl\w*\s+(ändern|aendern|umbauen|kürzen|kuerzen|absägen|entfernen|öffnen)",
            r"(sparren|kehlbalken|pfette)\w*\s+(kürzen|kuerzen|durchsägen|absägen|entfernen)",
            r"st(ü|ue)tze\s+entfernen",
            r"tr(ä|ae)ger\s+(einziehen|entfernen)",
        ),
        response=(
            "Eingriffe in tragende Bauteile (Wände, Decken, Dachstuhl) betreffen die "
            "Standsicherheit des Gebäudes und brauchen einen Tragwerksplaner – oft auch eine "
            "Genehmigung. Dafür erstelle ich keine Anleitung, kann dir aber helfen, die Fragen "
            "an den Planer vorzubereiten."
        ),
    ),
    SafetyTopic(
        key="hazardous",
        pattern=_p(
            r"asbest",
            r"eternit",
            r"nachtspeicher",
            r"\bpcp\b",
            r"lindan",
            r"teer(pappe|kleber)",
        ),
        response=(
            "Bei Verdacht auf Asbest oder alte Holzschutzmittel (z. B. PCP, Lindan) – typisch "
            "für Bauten und Materialien vor 1993 – bitte nichts selbst entfernen, schleifen oder "
            "bohren. Das dürfen nur Fachbetriebe mit Sachkunde nach TRGS 519. Lass das Material "
            "vorher prüfen."
        ),
    ),
)


@dataclass(frozen=True)
class SafetyVerdict:
    blocked: bool
    topic: str | None = None
    response: str | None = None


def check_message(text: str) -> SafetyVerdict:
    for topic in TOPICS:
        if topic.pattern.search(text):
            return SafetyVerdict(blocked=True, topic=topic.key, response=topic.response)
    return SafetyVerdict(blocked=False)

"""The "Warum so?" text of a block: fixed German paragraphs, so a block design needs no model call
for its documentation. They say only what the block builds."""

from __future__ import annotations

from homeworking.construction_model.pipeline import BlockSpec

_HOUSE_WALL = {
    "fachwerk": (
        "Die Wände sind Fachwerk: kräftige Pfosten zwischen Schwelle und Rähm, in den Ecken durch "
        "Streben ausgesteift, die das Haus gegen seitliche Kräfte (Wind) halten. Die Gefache sind "
        "mit Lehm ausgefacht; er speichert Wärme und Feuchte."
    ),
    "stud": (
        "Die Wände sind Ständerwerk: schlanke Ständer im Abstand von höchstens 62,5 cm zwischen "
        "Schwelle und Rähm, mit Holzfaserdämmung gefüllt und außen mit Lärchenschalung verkleidet."
    ),
}


def explain(block: BlockSpec) -> str:
    """Explanation paragraphs for one block module."""
    match block.kind:
        case "house":
            roof = (
                "Das Dach ist ein Satteldach: Dachbalken liegen auf den Rähmen und tragen die "
                "Sparren, die am First zusammenstoßen. Der Überstand schützt die Wände vor Regen."
                if block.roof != "flat"
                else "Das Dach ist flach: Dachbalken liegen auf den Rähmen und tragen die "
                "Eindeckung. Der Überstand schützt die Wände vor Regen."
            )
            return "\n\n".join(
                [
                    "Das Haus steht auf Punktfundamenten aus Beton, damit kein Holz im Erdreich "
                    "liegt und alles trocken bleibt. Darauf liegen Unterzüge und Bodenbalken, die "
                    "den Boden tragen.",
                    _HOUSE_WALL[block.frame]
                    + " Türen und Fenster sitzen zwischen Pfosten, mit Sturz und Brüstungsriegel.",
                    roof,
                ]
            )
        case "carcass":
            return (
                "Der Korpus besteht aus Birkensperrholz: Es ist formstabil und lässt sich sauber "
                "zuschneiden. Die Seitenteile tragen Boden, Deckel und Fachböden; die dünne "
                "Rückwand hält den Korpus rechtwinklig."
            )
        case "platform":
            return (
                "Das Podest ist ein Kasten aus Sperrholz: Zargen und Rippen im Abstand von höchstens "
                "60 cm tragen die Trittfläche, sodass sie sich auch bei Belastung nicht durchbiegt."
            )
        case "table":
            return (
                "Die Platte liegt auf einem Rahmen aus Zargen zwischen vier Beinen: Die Zargen "
                "halten die Beine rechtwinklig und verhindern, dass der Tisch wackelt."
            )
        case "post_frame":
            return (
                "Pfosten tragen zwei Pfetten, darauf liegen die Sparren. Beim Pultdach sind die "
                "Pfosten auf einer Seite höher, damit Wasser ablaufen kann; die Sparren stehen "
                "mit Waagschnitt auf der niedrigen und stoßen mit Lotschnitt an die hohe Pfette."
            )
        case "fence":
            return (
                "Pfosten im Abstand von höchstens zwei Metern tragen zwei Riegel; die senkrechten "
                "Latten sind auf die Riegel geschraubt, so bleibt der Zaun stabil und das Wasser "
                "läuft ab."
            )
    return ""

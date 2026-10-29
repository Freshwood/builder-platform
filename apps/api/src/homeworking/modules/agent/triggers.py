"""German phrasings the model router and the offline model both react to.

They live here, not in ``offline.py``, so that routing (production code) does not import the
offline test model.
"""

from __future__ import annotations

import re

NUM = r"(\d+(?:[.,]\d+)?)"
UNIT = r"(mm|cm|m)\b"

DELTA = re.compile(
    rf"{NUM}\s*{UNIT}\s*(breiter|schmaler|l(?:ä|ae)nger|k(?:ü|ue)rzer|h(?:ö|oe)her|niedriger)",
    re.IGNORECASE,
)
DELTA_PARAM = {
    "breiter": ("width_mm", 1),
    "schmaler": ("width_mm", -1),
    "länger": ("length_mm", 1),
    "laenger": ("length_mm", 1),
    "kürzer": ("length_mm", -1),
    "kuerzer": ("length_mm", -1),
    "höher": ("height_mm", 1),
    "hoeher": ("height_mm", 1),
    "niedriger": ("height_mm", -1),
}
VARIANTS = {
    "günstig": "budget",
    "guenstig": "budget",
    "langlebig": "durable",
    "komfort": "comfort",
}

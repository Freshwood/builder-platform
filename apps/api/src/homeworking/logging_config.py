"""Structured logs: one JSON object per line, including the ``extra`` fields of a record.

Agent turns log tokens, latency, model, prompt version and fingerprint this way
(``agent_turn`` / ``agent_turn_done``), so they can be analysed without the database.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; everything else came in via ``extra=``.
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        entry |= {k: v for k, v in record.__dict__.items() if k not in _STANDARD}
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Log ``homeworking.*`` as JSON to stderr unless the host already configured it."""
    logger = logging.getLogger("homeworking")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

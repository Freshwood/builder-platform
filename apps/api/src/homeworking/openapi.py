"""Print the OpenAPI schema (used to generate the TypeScript client)."""

from __future__ import annotations

import json
import sys

from homeworking.main import create_app
from homeworking.settings import Settings


def main() -> None:
    app = create_app(Settings(environment="test", database_url="sqlite+aiosqlite://"))
    json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

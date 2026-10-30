"""Write the API's OpenAPI schema to a file, for generating frontend types.

    uv run python -m screening_room.openapi ../frontend/openapi.json

No server needs to run and no database is contacted: FastAPI builds the schema
from the route definitions alone.
"""

import json
import sys
from pathlib import Path

from screening_room.config import Settings
from screening_room.main import create_app

# create_app() requires a database URL, but building the schema never connects
# (SQLAlchemy engines connect lazily), so a placeholder is enough.
_UNUSED_DATABASE_URL = "postgresql+psycopg://unused@localhost/unused"


def export_openapi(output: Path) -> None:
    schema = create_app(Settings(database_url=_UNUSED_DATABASE_URL)).openapi()
    # Stable formatting and "\n" line endings on every OS, so regenerating an
    # unchanged API changes nothing (Windows would otherwise write "\r\n").
    output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m screening_room.openapi <output.json>")
    export_openapi(Path(sys.argv[1]))

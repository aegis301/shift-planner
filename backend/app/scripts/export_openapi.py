from __future__ import annotations

import json
import sys

from app.main import app


def render_openapi() -> str:
    schema = app.openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> None:
    sys.stdout.write(render_openapi())


if __name__ == "__main__":
    main()

"""Write the OpenAPI schema to frontend/openapi.json (then: cd frontend && npm run gen:api)."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("PS_MASTER_DATABASE_URL", "sqlite://")
os.environ.setdefault("PS_EXPOSE_DOCS", "true")

from app.main import create_app

out = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
out.write_text(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {out}")

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from malo_ai.main import app

destination = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("docs/openapi.json exported")

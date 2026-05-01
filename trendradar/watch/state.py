# coding=utf-8
"""关注项状态持久化。"""

import json
from pathlib import Path
from typing import Any, Dict


class WatchStateStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"watches": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"watches": {}}

    def save(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

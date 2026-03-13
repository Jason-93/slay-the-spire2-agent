from __future__ import annotations

import json
from pathlib import Path

from sts2_agent.models import TraceEntry, to_dict


class JsonlTraceRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: TraceEntry) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(to_dict(entry), ensure_ascii=False) + "\n")

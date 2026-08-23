"""Prompt-hash keyed response cache for L2 (plan.md #14/#20).

Committed to `data/cache/` (see .gitignore's explicit carve-out) so a benchmark rerun costs
$0 and needs no API key -- plan.md #20 calls this out directly: "this doubles as a
reproducibility guarantee." That matters more than usual here, because current Claude models
don't support the `temperature 0` sampling control plan.md's L2 spec originally called for (see
client.py's module docstring) -- this cache, not live sampling determinism, is what actually
makes repeated benchmark/demo runs reproducible.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DEFAULT_CACHE_DIR = Path("data/cache/l2")


class ResponseCache:
    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, key: str) -> Optional[dict]:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, key: str, value: dict) -> None:
        self._path(key).write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")

"""Dziennik zmian w reklamach (odpowiednik „change log” ze Scale Insights).

Każda zmiana wykonana przez narzędzia reklam (confirm=true) dopisuje jedną linię JSON:
kiedy (UTC), co, w którym profilu (kraju), stan przed i po, wynik z Amazona.
Plik: ADS_CHANGE_LOG z .env, domyślnie data/ads-changes.jsonl w katalogu projektu.
Na VPS kontener jest tylko do odczytu, więc ścieżka musi wskazywać wolumen (/dane/ads-changes.jsonl).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "ads-changes.jsonl"


def log_path() -> Path:
    return Path(os.getenv("ADS_CHANGE_LOG", "").strip() or _DEFAULT)


def log_change(action: str, profile_id: str | None, items: list[dict[str, Any]], result: dict[str, Any]) -> str:
    """Zapisuje zmianę. Zwraca ścieżkę pliku albo opis błędu (zmiana na Amazonie i tak już poszła)."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "profile_id": profile_id,
        "items": items,
        "result": result,
    }
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        return f"NIE ZAPISANO do dziennika ({path}): {exc}"
    return str(path)


def read_changes(limit: int = 50, contains: str | None = None) -> list[dict[str, Any]]:
    path = log_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if contains:
        lines = [line for line in lines if contains.lower() in line.lower()]
    return [json.loads(line) for line in lines[-limit:]][::-1]

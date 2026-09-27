"""Wspólne elementy narzędzi: adnotacje i ochrona operacji zapisu."""

from __future__ import annotations

from typing import Any, Callable

from mcp.types import ToolAnnotations

from amazon_mcp.client import spapi

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)


def guarded_write(confirm: bool, action: str, request: dict[str, Any], execute: Callable[[], dict]) -> dict:
    """Operacja zapisu: bez confirm=True zwraca tylko podgląd tego, co zostałoby wysłane."""
    if not confirm:
        return {
            "status": "preview",
            "mode": spapi.mode,
            "action": action,
            "request": request,
            "note": "Nic nie zostało wysłane. Wywołaj ponownie z confirm=true, aby wykonać.",
        }
    spapi.ensure_writes_allowed()
    return {"status": "executed", "action": action, **execute()}

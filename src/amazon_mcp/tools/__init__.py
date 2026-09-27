"""Moduły narzędzi MCP. Każdy moduł ma funkcję register(mcp).

Aby dodać nową kategorię SP-API: utwórz plik w tym katalogu z funkcją
register(mcp) i dopisz go do listy MODULES poniżej.
"""

from amazon_mcp.tools import (
    advertising,
    catalog,
    feeds,
    fees,
    finances,
    inventory,
    listings,
    orders,
    pricing,
    reports,
    sellers,
)

MODULES = [
    sellers,
    orders,
    inventory,
    pricing,
    listings,
    catalog,
    reports,
    finances,
    fees,
    feeds,
    advertising,
]


def register_all(mcp) -> None:
    for module in MODULES:
        module.register(mcp)

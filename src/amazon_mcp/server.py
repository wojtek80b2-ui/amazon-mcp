"""Punkt wejścia serwera MCP."""

from __future__ import annotations

import argparse

from mcp.server.mcpserver import MCPServer

from amazon_mcp import __version__
from amazon_mcp.client import spapi
from amazon_mcp.tools import register_all

INSTRUCTIONS = """\
Serwer daje dostęp do konta sprzedawcy Amazon (Seller Central) przez Selling Partner API.
- Na start wywołaj server_status: w trybie "mock" dane są testowe, nie prawdziwe.
- Operacje zapisu (update_price, update_listing, create_listing, delete_listing, update_ad_campaign)
  najpierw wywołuj bez confirm, pokaż użytkownikowi podgląd i dopiero po jego zgodzie wywołaj z confirm=true.
- Parametr marketplace to kod kraju (PL, DE, FR, ...); domyślny jest ustawiony w .env.
- Reklamy (Amazon Ads API): list_ad_campaigns daje kampanie, a wyniki i ACoS dają
  request_ad_report + get_ad_report (raport tworzy się asynchronicznie).
- Odpowiedzi z next_token są stronicowane: przekaż token w kolejnym wywołaniu.
"""


def build_server() -> MCPServer:
    mcp = MCPServer(name="amazon-seller", version=__version__, instructions=INSTRUCTIONS)
    register_all(mcp)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Serwer MCP dla Amazon Seller Central")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio",
                        help="stdio dla Claude Desktop/Code lokalnie; streamable-http dla VPS")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    mcp = build_server()
    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

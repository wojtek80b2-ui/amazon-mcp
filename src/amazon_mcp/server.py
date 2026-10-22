"""Punkt wejścia serwera MCP."""

from __future__ import annotations

import argparse
import os

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
- Odpowiedzi z next_token są stronicowane: przekaż token w kolejnym wywołaniu.
"""


def build_server() -> MCPServer:
    mcp = MCPServer(name="amazon-seller", version=__version__, instructions=INSTRUCTIONS)
    register_all(mcp)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Serwer MCP dla Amazon Seller Central")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default=os.getenv("MCP_TRANSPORT", "stdio"),
                        help="stdio dla Claude Desktop/Code lokalnie; streamable-http dla VPS")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8000")))
    args = parser.parse_args()

    mcp = build_server()
    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        run_http(mcp, args.host, args.port)


def run_http(mcp: MCPServer, host: str, port: int) -> None:
    """Tryb VPS: HTTP z tokenami z MCP_TOKENS (HTTPS zapewnia reverse proxy)."""
    import logging

    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    from amazon_mcp.http_auth import BearerAuthMiddleware, load_tokens

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # MCP_ALLOWED_HOSTS: domena(y), pod którą serwer jest widoczny, np. mcp.example.com
    allowed = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(allowed),
        allowed_hosts=allowed + [f"{h}:*" for h in allowed],
    )
    app = mcp.streamable_http_app(transport_security=security, host=host)
    # Nagłówki X-Forwarded-* tylko od proxy: port serwera nie może być wystawiony poza sieć proxy.
    uvicorn.run(BearerAuthMiddleware(app, load_tokens()), host=host, port=port,
                proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()

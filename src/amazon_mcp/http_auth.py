"""Uwierzytelnianie tokenem (Bearer) dla trybu HTTP na VPS.

Token w nagłówku "Authorization: Bearer <token>" albo "X-MCP-Token: <token>".
Tokeny są w zmiennej MCP_TOKENS w formacie "nazwa:token,nazwa:token", np.
MCP_TOKENS=wojtek:abc123...,ola:def456...
Każda osoba ma swój token: można go odebrać jednej osobie bez ruszania drugiej,
a w logu widać, kto wywołał narzędzie.
"""

from __future__ import annotations

import hmac
import json
import logging
import os

log = logging.getLogger("amazon_mcp.auth")


def load_tokens() -> dict[str, str]:
    """Zwraca {token: nazwa_użytkownika} z MCP_TOKENS."""
    tokens: dict[str, str] = {}
    for entry in os.getenv("MCP_TOKENS", "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, token = entry.partition(":")
        if not sep or len(token.strip()) < 32:
            raise ValueError(f"MCP_TOKENS: wpis '{name}' musi mieć format nazwa:token (token min. 32 znaki)")
        tokens[token.strip()] = name.strip()
    return tokens


class BearerAuthMiddleware:
    """Middleware ASGI: przepuszcza tylko żądania z poprawnym nagłówkiem Authorization."""

    def __init__(self, app, tokens: dict[str, str]):
        if not tokens:
            raise ValueError("Brak MCP_TOKENS: serwer HTTP nie wystartuje bez uwierzytelniania")
        self.app = app
        self.tokens = tokens

    def _user_for(self, header: str) -> str | None:
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return self._user_for_token(token)

    def _user_for_token(self, token: str) -> str | None:
        if not token:
            return None
        for known, user in self.tokens.items():
            if hmac.compare_digest(known.encode(), token.strip().encode()):
                return user
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope.get("path") == "/health":
            return await _respond(send, 200, {"status": "ok"})

        headers = dict(scope.get("headers") or [])
        # Bramka Pomerium (tryb MCP) nie przekazuje własnego nagłówka Authorization,
        # więc token od niej przychodzi w X-MCP-Token.
        user = self._user_for(headers.get(b"authorization", b"").decode("latin-1")) or self._user_for_token(
            headers.get(b"x-mcp-token", b"").decode("latin-1")
        )
        if user is None:
            client = (scope.get("client") or ("?",))[0]
            log.warning("Odrzucono żądanie bez poprawnego tokenu z %s", client)
            return await _respond(send, 401, {"error": "unauthorized"}, {"www-authenticate": "Bearer"})

        scope.setdefault("state", {})["mcp_user"] = user
        log.info("%s %s %s", user, scope.get("method"), scope.get("path"))
        return await self.app(scope, receive, send)


async def _respond(send, status: int, body: dict, extra_headers: dict[str, str] | None = None) -> None:
    payload = json.dumps(body).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    headers += [(k.encode(), v.encode()) for k, v in (extra_headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})

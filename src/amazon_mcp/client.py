"""Jedno miejsce, przez które przechodzą wszystkie wywołania SP-API.

W trybie mock zwraca dane testowe, w trybie live woła prawdziwe API przez
bibliotekę python-amazon-sp-api (obsługuje logowanie LWA, odświeżanie tokenów,
podpisywanie zapytań i limity).

Dodanie nowego endpointu = jedna linijka w module narzędzi:

    spapi.call("OrdersV0", "get_orders", mock=lambda: MOCK_ORDERS, CreatedAfter=...)
"""

from __future__ import annotations

from typing import Any, Callable

from amazon_mcp.config import Settings, settings as default_settings


class AmazonAPIError(RuntimeError):
    """Błąd zwrócony przez SP-API, w formie czytelnej dla Claude."""


class WriteBlockedError(RuntimeError):
    """Zapis zablokowany konfiguracją AMAZON_ALLOW_WRITES=false."""


class SPAPIClient:
    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or default_settings

    # ------------------------------------------------------------------ helpers
    @property
    def mode(self) -> str:
        return "mock" if self.cfg.is_mock else "live"

    def marketplace(self, code: str | None = None):
        from sp_api.base import Marketplaces

        code = (code or self.cfg.marketplace).upper()
        try:
            return Marketplaces[code]
        except KeyError as exc:
            valid = ", ".join(m.name for m in Marketplaces)
            raise AmazonAPIError(f"Nieznany marketplace '{code}'. Dostępne: {valid}") from exc

    def marketplace_id(self, code: str | None = None) -> str:
        return self.marketplace(code).marketplace_id

    def seller_id(self) -> str:
        if self.cfg.is_mock:
            return self.cfg.seller_id or "A1MOCKSELLER"
        if not self.cfg.seller_id:
            raise AmazonAPIError("Brak SP_API_SELLER_ID w pliku .env (wymagane dla Listings API).")
        return self.cfg.seller_id

    def ensure_writes_allowed(self) -> None:
        if not self.cfg.allow_writes:
            raise WriteBlockedError("Zapis wyłączony (AMAZON_ALLOW_WRITES=false).")

    # --------------------------------------------------------------------- call
    def call(
        self,
        api: str,
        method: str,
        *args: Any,
        mock: Callable[[], Any] | Any = None,
        marketplace: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Wywołaj metodę klienta SP-API, np. call("Reports", "get_reports", reportTypes=[...])."""
        if self.cfg.is_mock:
            data = mock() if callable(mock) else mock
            return {"mode": "mock", "payload": data}

        missing = self.cfg.missing_sp_api_credentials()
        if missing:
            raise AmazonAPIError(
                "Tryb live, ale brakuje poświadczeń w .env: " + ", ".join(missing)
            )

        import sp_api.api as sp_api_module
        from sp_api.base import SellingApiException

        api_cls = getattr(sp_api_module, api)
        client = api_cls(
            marketplace=self.marketplace(marketplace),
            credentials=self.cfg.sp_api_credentials,
        )
        try:
            response = getattr(client, method)(*args, **kwargs)
        except SellingApiException as exc:
            raise AmazonAPIError(f"SP-API {api}.{method}: {exc}") from exc

        result: dict[str, Any] = {"mode": "live", "payload": response.payload}
        if getattr(response, "next_token", None):
            result["next_token"] = response.next_token
        return result


spapi = SPAPIClient()

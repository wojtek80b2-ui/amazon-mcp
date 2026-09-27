"""Amazon Advertising API (Sponsored Products).

Uwaga: reklamy to OSOBNE API (advertising-api.amazon.com), nie część SP-API.
Wymaga osobnej rejestracji i kluczy (ADS_API_* w .env). Na razie działa w trybie
mock; w trybie live zwraca instrukcję, co trzeba dodać.
"""

from amazon_mcp import mock_data
from amazon_mcp.client import AmazonAPIError, spapi
from amazon_mcp.tools._common import READ_ONLY, WRITE, guarded_write


def _live_not_ready() -> None:
    raise AmazonAPIError(
        "Advertising API nie jest jeszcze podłączone w trybie live. Potrzebne: dostęp do Amazon Ads API "
        "(advertising.amazon.com/API), klucze ADS_API_* w .env oraz implementacja w tools/advertising.py "
        "(np. biblioteka python-amazon-ad-api)."
    )


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def list_ad_campaigns(state: str | None = None) -> dict:
        """Kampanie Sponsored Products z budżetem i wynikami (wyświetlenia, kliknięcia, koszt, sprzedaż, ACoS).

        state: ENABLED, PAUSED, ARCHIVED.
        """
        if not spapi.cfg.is_mock:
            _live_not_ready()
        campaigns = [c for c in mock_data.AD_CAMPAIGNS if not state or c["state"] == state.upper()]
        return {"mode": "mock", "payload": {"campaigns": campaigns}}

    @mcp.tool(annotations=WRITE)
    def update_ad_campaign(
        campaign_id: str,
        state: str | None = None,
        daily_budget: float | None = None,
        confirm: bool = False,
    ) -> dict:
        """Zmień stan (ENABLED/PAUSED) lub dzienny budżet kampanii. Bez confirm=true tylko podgląd."""
        changes = {k: v for k, v in {"state": state, "dailyBudget": daily_budget}.items() if v is not None}

        def execute():
            if not spapi.cfg.is_mock:
                _live_not_ready()
            return {"mode": "mock", "payload": {"campaignId": campaign_id, "code": "SUCCESS", **changes}}

        return guarded_write(confirm, f"Zmiana kampanii {campaign_id}", {"campaignId": campaign_id, **changes}, execute)

"""Sellers API + status serwera."""

from amazon_mcp import mock_data
from amazon_mcp.ads_client import AdsClient
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def server_status() -> dict:
        """Pokaż tryb pracy serwera (mock/live), domyślny marketplace i brakujące poświadczenia."""
        cfg = spapi.cfg
        return {
            "mode": spapi.mode,
            "default_marketplace": cfg.marketplace,
            "seller_id_set": bool(cfg.seller_id),
            "missing_sp_api_credentials": cfg.missing_sp_api_credentials(),
            "ads_region": cfg.ads_region,
            "missing_ads_api_credentials": AdsClient(cfg).missing_credentials(),
            "writes_allowed": cfg.allow_writes,
        }

    @mcp.tool(annotations=READ_ONLY)
    def get_marketplace_participation() -> dict:
        """Lista marketplace'ów, na których konto sprzedawcy jest aktywne (Sellers API)."""
        return spapi.call("Sellers", "get_marketplace_participation",
                          mock=mock_data.MARKETPLACE_PARTICIPATION)

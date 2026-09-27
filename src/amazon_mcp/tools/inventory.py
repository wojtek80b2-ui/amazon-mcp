"""FBA Inventory API v1."""

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def get_fba_inventory(
        skus: list[str] | None = None,
        marketplace: str | None = None,
        next_token: str | None = None,
    ) -> dict:
        """Stany magazynowe FBA: dostępne, zarezerwowane i w drodze do magazynu Amazon.

        skus: opcjonalnie do 50 SKU; bez tego zwraca cały magazyn (stronicowany).
        """
        mid = spapi.marketplace_id(marketplace)
        params = {"details": True, "granularityType": "Marketplace", "granularityId": mid, "marketplaceIds": [mid]}
        if skus:
            params["sellerSkus"] = skus
        if next_token:
            params["nextToken"] = next_token

        def mock():
            data = dict(mock_data.FBA_INVENTORY)
            if skus:
                data["inventorySummaries"] = [s for s in data["inventorySummaries"] if s["sellerSku"] in skus]
            return data

        return spapi.call("Inventories", "get_inventory_summary_marketplace", mock=mock,
                          marketplace=marketplace, **params)

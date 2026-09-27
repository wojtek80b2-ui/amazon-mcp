"""Catalog Items API 2022-04-01."""

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY

INCLUDED_DATA = ["summaries", "attributes", "images", "salesRanks", "identifiers"]


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def search_catalog(
        keywords: list[str] | None = None,
        identifiers: list[str] | None = None,
        identifiers_type: str = "ASIN",
        marketplace: str | None = None,
    ) -> dict:
        """Szukaj produktów w katalogu Amazon po słowach kluczowych albo identyfikatorach.

        identifiers_type: ASIN, EAN, GTIN, ISBN, JAN, MINSAN, SKU, UPC.
        """
        params = {"marketplaceIds": [spapi.marketplace_id(marketplace)], "includedData": ["summaries", "salesRanks"]}
        if keywords:
            params["keywords"] = keywords
        if identifiers:
            params["identifiers"] = identifiers
            params["identifiersType"] = identifiers_type
        return spapi.call("CatalogItemsV20220401", "search_catalog_items", marketplace=marketplace,
                          mock={"numberOfResults": 1, "items": [mock_data.CATALOG_ITEM]}, **params)

    @mcp.tool(annotations=READ_ONLY)
    def get_catalog_item(asin: str, marketplace: str | None = None) -> dict:
        """Dane katalogowe ASIN-u: tytuł, marka, zdjęcia, ranking sprzedaży (BSR)."""
        return spapi.call("CatalogItemsV20220401", "get_catalog_item", asin,
                          marketplaceIds=[spapi.marketplace_id(marketplace)], includedData=INCLUDED_DATA,
                          marketplace=marketplace, mock={**mock_data.CATALOG_ITEM, "asin": asin})

"""Listings Items API 2021-08-01."""

from typing import Any

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import DESTRUCTIVE, READ_ONLY, WRITE, guarded_write

INCLUDED_DATA = ["summaries", "attributes", "issues", "offers", "fulfillmentAvailability"]


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def search_listings(
        skus: list[str] | None = None,
        page_size: int = 20,
        page_token: str | None = None,
        marketplace: str | None = None,
    ) -> dict:
        """Lista Twoich ofert (listingów) z podsumowaniem, statusem i problemami."""
        params: dict[str, Any] = {"marketplaceIds": [spapi.marketplace_id(marketplace)],
                                  "includedData": ["summaries", "issues"], "pageSize": min(page_size, 20)}
        if skus:
            params["identifiers"] = skus
            params["identifiersType"] = "SKU"
        if page_token:
            params["pageToken"] = page_token

        def mock():
            items = mock_data.LISTINGS_SEARCH["items"]
            if skus:
                items = [i for i in items if i["sku"] in skus]
            return {"numberOfResults": len(items), "items": items}

        return spapi.call("ListingsItemsV20210801", "search_listings_items", spapi.seller_id(),
                          marketplace=marketplace, mock=mock, **params)

    @mcp.tool(annotations=READ_ONLY)
    def get_listing(sku: str, marketplace: str | None = None) -> dict:
        """Szczegóły listingu: atrybuty, oferta, status, problemy (issues), typ produktu."""
        return spapi.call("ListingsItemsV20210801", "get_listings_item", spapi.seller_id(), sku,
                          marketplaceIds=[spapi.marketplace_id(marketplace)], includedData=INCLUDED_DATA,
                          marketplace=marketplace, mock=lambda: mock_data.listing(sku))

    @mcp.tool(annotations=WRITE)
    def update_listing(
        sku: str,
        product_type: str,
        patches: list[dict],
        marketplace: str | None = None,
        confirm: bool = False,
    ) -> dict:
        """Częściowa aktualizacja listingu (JSON Patch). Bez confirm=true tylko podgląd.

        Przykład patches: [{"op": "replace", "path": "/attributes/item_name",
                            "value": [{"value": "Nowy tytuł", "language_tag": "pl_PL"}]}]
        """
        body = {"productType": product_type, "patches": patches}
        mid = spapi.marketplace_id(marketplace)
        return guarded_write(
            confirm, f"Aktualizacja listingu {sku}", body,
            lambda: spapi.call("ListingsItemsV20210801", "patch_listings_item", spapi.seller_id(), sku,
                               body=body, marketplaceIds=[mid], marketplace=marketplace,
                               mock={"sku": sku, "status": "ACCEPTED", "submissionId": "mock-submission"}),
        )

    @mcp.tool(annotations=WRITE)
    def create_listing(
        sku: str,
        product_type: str,
        attributes: dict,
        requirements: str = "LISTING",
        marketplace: str | None = None,
        confirm: bool = False,
    ) -> dict:
        """Utwórz albo w pełni nadpisz listing (PUT). Bez confirm=true tylko podgląd.

        requirements: LISTING (produkt + oferta), LISTING_OFFER_ONLY (oferta do istniejącego ASIN),
        LISTING_PRODUCT_ONLY. Wymagane atrybuty zależą od product_type (Product Type Definitions API).
        """
        body = {"productType": product_type, "requirements": requirements, "attributes": attributes}
        mid = spapi.marketplace_id(marketplace)
        return guarded_write(
            confirm, f"Utworzenie/nadpisanie listingu {sku}", body,
            lambda: spapi.call("ListingsItemsV20210801", "put_listings_item", spapi.seller_id(), sku,
                               body=body, marketplaceIds=[mid], marketplace=marketplace,
                               mock={"sku": sku, "status": "ACCEPTED", "submissionId": "mock-submission"}),
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_listing(sku: str, marketplace: str | None = None, confirm: bool = False) -> dict:
        """Usuń listing (ofertę) z marketplace'u. Nieodwracalne. Bez confirm=true tylko podgląd."""
        mid = spapi.marketplace_id(marketplace)
        return guarded_write(
            confirm, f"USUNIĘCIE listingu {sku}", {"sku": sku, "marketplaceIds": [mid]},
            lambda: spapi.call("ListingsItemsV20210801", "delete_listings_item", spapi.seller_id(), sku,
                               marketplaceIds=[mid], marketplace=marketplace,
                               mock={"sku": sku, "status": "ACCEPTED"}),
        )

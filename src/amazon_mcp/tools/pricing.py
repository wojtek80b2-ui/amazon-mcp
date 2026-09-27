"""Product Pricing API v0 + zmiana ceny przez Listings Items API."""

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY, WRITE, guarded_write


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def get_competitive_pricing(asins: list[str], marketplace: str | None = None) -> dict:
        """Ceny konkurencyjne (m.in. cena Buy Box) dla maks. 20 ASIN-ów."""
        return spapi.call("ProductsV0", "get_competitive_pricing_for_asins", asins[:20],
                          marketplace=marketplace,
                          mock=lambda: [p for p in mock_data.COMPETITIVE_PRICING if p["ASIN"] in asins])

    @mcp.tool(annotations=READ_ONLY)
    def get_my_prices(skus: list[str], marketplace: str | None = None) -> dict:
        """Twoje aktualne ceny dla maks. 20 SKU."""
        def mock():
            return [{"SellerSKU": p["sku"], "status": "Success",
                     "Product": {"Offers": [{"BuyingPrice": {"ListingPrice": {"CurrencyCode": "PLN",
                                                                              "Amount": f"{p['price']:.2f}"}}}]}}
                    for p in mock_data.PRODUCTS if p["sku"] in skus]

        return spapi.call("ProductsV0", "get_product_pricing_for_skus", skus[:20],
                          marketplace=marketplace, mock=mock)

    @mcp.tool(annotations=READ_ONLY)
    def get_item_offers(asin: str, item_condition: str = "New", marketplace: str | None = None) -> dict:
        """Wszystkie oferty dla ASIN-u: kto ma Buy Box, najniższe ceny, liczba ofert."""
        return spapi.call("ProductsV0", "get_item_offers", asin, item_condition,
                          marketplace=marketplace, mock=lambda: mock_data.item_offers(asin))

    @mcp.tool(annotations=WRITE)
    def update_price(
        sku: str,
        price: float,
        product_type: str,
        currency: str = "PLN",
        marketplace: str | None = None,
        confirm: bool = False,
    ) -> dict:
        """Zmień cenę oferty (cena brutto z VAT). Bez confirm=true pokazuje tylko podgląd.

        product_type: typ produktu z listingu (sprawdź narzędziem get_listing, pole productType).
        """
        mid = spapi.marketplace_id(marketplace)
        body = {
            "productType": product_type,
            "patches": [{
                "op": "replace",
                "path": "/attributes/purchasable_offer",
                "value": [{"marketplace_id": mid, "currency": currency,
                           "our_price": [{"schedule": [{"value_with_tax": price}]}]}],
            }],
        }
        return guarded_write(
            confirm, f"Zmiana ceny {sku} na {price:.2f} {currency}", body,
            lambda: spapi.call("ListingsItemsV20210801", "patch_listings_item", spapi.seller_id(), sku,
                               body=body, marketplaceIds=[mid], marketplace=marketplace,
                               mock={"sku": sku, "status": "ACCEPTED", "submissionId": "mock-submission"}),
        )

"""Orders API v0."""

from datetime import datetime, timedelta, timezone

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def list_orders(
        created_after: str | None = None,
        created_before: str | None = None,
        statuses: list[str] | None = None,
        fulfillment_channels: list[str] | None = None,
        marketplace: str | None = None,
        max_results: int = 50,
        next_token: str | None = None,
    ) -> dict:
        """Lista zamówień. Daty w ISO 8601 (np. 2026-09-01T00:00:00Z); domyślnie ostatnie 7 dni.

        statuses: Pending, Unshipped, PartiallyShipped, Shipped, Canceled, Unfulfillable.
        fulfillment_channels: AFN (FBA) albo MFN (własna wysyłka).
        """
        if next_token:
            params = {"NextToken": next_token}
        else:
            after = created_after or (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            params = {"CreatedAfter": after, "MarketplaceIds": [spapi.marketplace_id(marketplace)],
                      "MaxResultsPerPage": min(max_results, 100)}
            if created_before:
                params["CreatedBefore"] = created_before
            if statuses:
                params["OrderStatuses"] = statuses
            if fulfillment_channels:
                params["FulfillmentChannels"] = fulfillment_channels

        def mock():
            orders = mock_data.ORDERS
            if statuses:
                orders = [o for o in orders if o["OrderStatus"] in statuses]
            if fulfillment_channels:
                orders = [o for o in orders if o["FulfillmentChannel"] in fulfillment_channels]
            return {"Orders": orders}

        return spapi.call("OrdersV0", "get_orders", mock=mock, marketplace=marketplace, **params)

    @mcp.tool(annotations=READ_ONLY)
    def get_order(order_id: str) -> dict:
        """Szczegóły jednego zamówienia (np. 405-0000001-0000001)."""
        return spapi.call("OrdersV0", "get_order", order_id,
                          mock=lambda: next((o for o in mock_data.ORDERS if o["AmazonOrderId"] == order_id), None))

    @mcp.tool(annotations=READ_ONLY)
    def get_order_items(order_id: str) -> dict:
        """Pozycje (produkty) w zamówieniu: SKU, ASIN, ilości, ceny."""
        return spapi.call("OrdersV0", "get_order_items", order_id,
                          mock=lambda: {"AmazonOrderId": order_id,
                                        "OrderItems": mock_data.ORDER_ITEMS.get(order_id, [])})

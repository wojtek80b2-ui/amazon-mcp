"""Testy w trybie mock: każde narzędzie się rejestruje i zwraca dane bez kluczy Amazon."""

import asyncio
import json
import os

os.environ["AMAZON_MODE"] = "mock"

import pytest

from amazon_mcp.server import build_server

EXPECTED_TOOLS = {
    "server_status", "get_marketplace_participation",
    "list_orders", "get_order", "get_order_items",
    "get_fba_inventory",
    "get_competitive_pricing", "get_my_prices", "get_item_offers", "update_price",
    "search_listings", "get_listing", "update_listing", "create_listing", "delete_listing",
    "search_catalog", "get_catalog_item",
    "list_reports", "create_report", "get_report", "get_report_document",
    "list_financial_events", "get_order_financial_events",
    "estimate_fees",
    "list_feeds", "get_feed",
    "list_ad_profiles", "list_ad_campaigns", "update_ad_campaign", "request_ad_report", "get_ad_report",
}


@pytest.fixture(scope="module")
def mcp():
    return build_server()


def call(mcp, name, **args):
    result = asyncio.run(mcp.call_tool(name, args))
    # call_tool zwraca treść i/lub dane strukturalne zależnie od wersji SDK
    if isinstance(result, tuple):
        result = result[1] if result[1] is not None else result[0]
    if isinstance(result, dict):
        return result.get("result", result)
    content = result if isinstance(result, list) else getattr(result, "content", result)
    return json.loads(content[0].text)


def test_all_tools_registered(mcp):
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert EXPECTED_TOOLS <= names


def test_status_is_mock(mcp):
    assert call(mcp, "server_status")["mode"] == "mock"


def test_orders_filter(mcp):
    data = call(mcp, "list_orders", statuses=["Unshipped"])
    assert [o["OrderStatus"] for o in data["payload"]["Orders"]] == ["Unshipped"]


def test_order_items(mcp):
    data = call(mcp, "get_order_items", order_id="405-0000001-0000001")
    assert data["payload"]["OrderItems"][0]["SellerSKU"] == "KUBEK-001"


def test_inventory(mcp):
    data = call(mcp, "get_fba_inventory", skus=["BUTELKA-002"])
    assert len(data["payload"]["inventorySummaries"]) == 1


def test_write_requires_confirm(mcp):
    preview = call(mcp, "update_price", sku="KUBEK-001", price=35.0, product_type="DRINKING_CUP")
    assert preview["status"] == "preview"
    done = call(mcp, "update_price", sku="KUBEK-001", price=35.0, product_type="DRINKING_CUP", confirm=True)
    assert done["status"] == "executed"


def test_delete_listing_preview(mcp):
    assert call(mcp, "delete_listing", sku="TORBA-003")["status"] == "preview"


def test_report_document(mcp):
    data = call(mcp, "get_report_document", report_document_id="amzn1.tortuga.mock.doc1")
    assert "KUBEK-001" in data["payload"]["document"]


def test_ads(mcp):
    data = call(mcp, "list_ad_campaigns", state="enabled")
    assert len(data["payload"]["campaigns"]) == 1

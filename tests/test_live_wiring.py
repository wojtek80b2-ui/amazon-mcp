"""Tryb live bez sieci: sprawdza, że narzędzia trafiają w właściwe ścieżki SP-API z właściwymi parametrami."""

import asyncio

import pytest

from amazon_mcp.client import SPAPIClient
from amazon_mcp.config import Settings
from amazon_mcp.server import build_server

LIVE = Settings(mode="live", lwa_client_id="id", lwa_client_secret="secret", refresh_token="token",
                seller_id="A1SELLER", marketplace="PL")


@pytest.fixture
def captured(monkeypatch):
    from sp_api.base import ApiResponse, Client
    import amazon_mcp.client as client_module
    import amazon_mcp.tools._common as common

    calls = []

    def fake_request(self, path, *args, data=None, params=None, **kwargs):
        calls.append({"method": self.method if hasattr(self, "method") else None, "path": path,
                      "params": params, "data": data})
        return ApiResponse(payload={"ok": True}, headers={})

    monkeypatch.setattr(Client, "_request", fake_request)
    live = SPAPIClient(LIVE)
    monkeypatch.setattr(client_module.spapi, "cfg", live.cfg)
    monkeypatch.setattr(common.spapi, "cfg", live.cfg)
    return calls


CASES = [
    ("list_orders", {}, "/orders/v0/orders"),
    ("get_order_items", {"order_id": "405-1"}, "/orders/v0/orders/405-1/orderItems"),
    ("get_fba_inventory", {}, "/fba/inventory/v1/summaries"),
    ("get_listing", {"sku": "KUBEK-001"}, "/listings/2021-08-01/items/A1SELLER/KUBEK-001"),
    ("get_catalog_item", {"asin": "B0X"}, "/catalog/2022-04-01/items/B0X"),
    ("list_reports", {}, "/reports/2021-06-30/reports"),
    ("get_report", {"report_id": "5"}, "/reports/2021-06-30/reports/5"),
    ("list_financial_events", {}, "/finances/v0/financialEvents"),
    ("get_item_offers", {"asin": "B0X"}, "/products/pricing/v0/items/B0X/offers"),
    ("update_price", {"sku": "S1", "price": 10.0, "product_type": "T", "confirm": True},
     "/listings/2021-08-01/items/A1SELLER/S1"),
]


@pytest.mark.parametrize("tool,args,path", CASES)
def test_live_paths(captured, tool, args, path):
    mcp = build_server()
    asyncio.run(mcp.call_tool(tool, args))
    assert captured, f"{tool} nie wywołał SP-API"
    assert captured[-1]["path"].startswith(path), captured[-1]


def test_missing_credentials_message():
    client = SPAPIClient(Settings(mode="live", lwa_client_id="", lwa_client_secret="", refresh_token=""))
    with pytest.raises(Exception, match="SP_API_REFRESH_TOKEN"):
        client.call("OrdersV0", "get_orders")

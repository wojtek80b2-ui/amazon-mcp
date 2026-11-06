"""Amazon Ads API w trybie live bez sieci: sprawdza token, nagłówki, ścieżki i treść zapytań."""

import asyncio
import gzip
import json

import httpx
import pytest

import amazon_mcp.tools.advertising as advertising
from amazon_mcp.ads_auth import consent_url, extract_code, set_env_value
from amazon_mcp.ads_client import AdsClient
from amazon_mcp.client import SPAPIClient
from amazon_mcp.config import Settings
from amazon_mcp.server import build_server

LIVE = Settings(mode="live", lwa_client_id="id", lwa_client_secret="secret", refresh_token="token",
                ads_client_id="ads-id", ads_client_secret="ads-secret", ads_refresh_token="Atzr|ads",
                ads_profile_id="111", ads_region="EU")


@pytest.fixture
def requests(monkeypatch):
    import amazon_mcp.client as client_module
    import amazon_mcp.tools._common as common

    seen = []
    report_rows = [{"campaignName": "A", "cost": 10.0, "sales7d": 40.0}, {"campaignName": "B", "cost": 5.0, "sales7d": 0}]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/auth/o2/token":
            return httpx.Response(200, json={"access_token": "Atza|tok", "expires_in": 3600})
        if request.url.path == "/sp/campaigns/list":
            return httpx.Response(200, json={"campaigns": [{"campaignId": "1"}], "nextToken": "n2"})
        if request.url.path == "/sp/campaigns":
            return httpx.Response(207, json={"campaigns": {"success": [{"campaignId": "1"}], "error": []}})
        if request.url.path == "/reporting/reports/r1":
            return httpx.Response(200, json={"status": "COMPLETED", "url": "https://dl.example/r1.json.gz"})
        if request.url.host == "dl.example":
            return httpx.Response(200, content=gzip.compress(json.dumps(report_rows).encode()))
        return httpx.Response(200, json=[{"profileId": 111, "countryCode": "DE"}])

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(advertising, "ads", AdsClient(LIVE, transport=transport))
    monkeypatch.setattr(advertising.httpx, "get", lambda url, **kw: httpx.Client(transport=transport).get(url))
    live = SPAPIClient(LIVE)
    monkeypatch.setattr(client_module.spapi, "cfg", live.cfg)
    monkeypatch.setattr(common.spapi, "cfg", live.cfg)
    return seen


def call(tool, args):
    result = asyncio.run(build_server().call_tool(tool, args))
    if getattr(result, "is_error", False):
        raise AssertionError(result.content[0].text)
    return json.loads(result.content[0].text)


def test_list_campaigns_live(requests):
    result = call("list_ad_campaigns", {"state": "enabled"})
    token_req, api_req = requests
    assert str(token_req.url) == "https://api.amazon.co.uk/auth/o2/token"
    assert api_req.url == "https://advertising-api-eu.amazon.com/sp/campaigns/list"
    assert api_req.headers["Amazon-Advertising-API-Scope"] == "111"
    assert api_req.headers["Amazon-Advertising-API-ClientId"] == "ads-id"
    assert api_req.headers["Authorization"] == "Bearer Atza|tok"
    assert api_req.headers["Content-Type"] == "application/vnd.spCampaign.v3+json"
    assert json.loads(api_req.content)["stateFilter"] == {"include": ["ENABLED"]}
    assert result["next_token"] == "n2"


def test_profiles_without_scope_header(requests):
    call("list_ad_profiles", {})
    assert requests[-1].url.path == "/v2/profiles"
    assert "Amazon-Advertising-API-Scope" not in requests[-1].headers


def test_update_campaign_live(requests):
    call("update_ad_campaign", {"campaign_id": "1", "daily_budget": 25.0, "state": "paused", "confirm": True})
    body = json.loads(requests[-1].content)
    assert requests[-1].method == "PUT"
    assert body == {"campaigns": [{"campaignId": "1", "state": "PAUSED",
                                   "budget": {"budget": 25.0, "budgetType": "DAILY"}}]}


def test_report_download_and_acos(requests):
    result = call("get_ad_report", {"report_id": "r1"})
    rows = result["payload"]["rows"]
    assert rows[0]["acos"] == 25.0 and rows[1]["acos"] is None


def test_missing_ads_credentials():
    client = AdsClient(Settings(mode="live", ads_client_id="x"))
    with pytest.raises(Exception, match="ADS_API_REFRESH_TOKEN"):
        client.request("GET", "/v2/profiles", profile_scope=False)


def test_auth_helpers(tmp_path):
    url = consent_url("cid", "EU", "https://www.amazon.de")
    assert url.startswith("https://eu.account.amazon.com/ap/oa?client_id=cid")
    assert "scope=advertising%3A%3Acampaign_management" in url
    assert extract_code("https://www.amazon.de/?code=ANabc&scope=advertising") == "ANabc"
    assert extract_code(" ANabc ") == "ANabc"

    env = tmp_path / ".env"
    env.write_text("AMAZON_MODE=live\nADS_API_REFRESH_TOKEN=\n")
    set_env_value(env, "ADS_API_REFRESH_TOKEN", "Atzr|x\\1")
    set_env_value(env, "ADS_API_PROFILE_ID", "111")
    assert env.read_text() == "AMAZON_MODE=live\nADS_API_REFRESH_TOKEN=Atzr|x\\1\nADS_API_PROFILE_ID=111\n"

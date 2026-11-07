"""Zarządzanie reklamami (stawki, negatywy, słowa, placementy, dziennik) w trybie live bez sieci."""

import asyncio
import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import amazon_mcp.tools.advertising as advertising
from amazon_mcp.ads_client import AdsClient
from amazon_mcp.client import SPAPIClient
from amazon_mcp.config import Settings
from amazon_mcp.server import build_server

LIVE = Settings(mode="live", lwa_client_id="id", lwa_client_secret="secret", refresh_token="token",
                ads_client_id="ads-id", ads_client_secret="ads-secret", ads_refresh_token="Atzr|ads",
                ads_profile_id="111", ads_region="EU")

KEYWORD = {"keywordId": "k1", "keywordText": "hundebett", "matchType": "EXACT", "bid": 0.5,
           "state": "ENABLED", "campaignId": "c1", "adGroupId": "g1"}
CAMPAIGN = {"campaignId": "c1", "name": "DE | SP | Test",
            "dynamicBidding": {"strategy": "LEGACY_FOR_SALES",
                               "placementBidding": [{"placement": "PLACEMENT_TOP", "percentage": 20},
                                                    {"placement": "PLACEMENT_PRODUCT_PAGE", "percentage": 0}]}}


@pytest.fixture
def api(monkeypatch, tmp_path):
    import amazon_mcp.client as client_module
    import amazon_mcp.tools._common as common

    monkeypatch.setenv("ADS_CHANGE_LOG", str(tmp_path / "log.jsonl"))
    seen = Seen()
    state = {"fail_path": None, "item_error": None}
    allowed_filters = {
        "keywords": "keywordIdFilter", "targets": "targetIdFilter",
        "negativeKeywords": "negativeKeywordIdFilter", "campaignNegativeKeywords": "campaignNegativeKeywordIdFilter",
        "negativeTargets": "negativeTargetIdFilter", "campaignNegativeTargets": "campaignNegativeTargetIdFilter",
    }

    def ok(key, ids):
        return httpx.Response(207, json={key: {"success": [{"index": i, "id": x} for i, x in enumerate(ids)],
                                               "error": []}})

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/auth/o2/token":
            return httpx.Response(200, json={"access_token": "Atza|tok", "expires_in": 3600})
        body = json.loads(request.content or b"{}")
        resource = path.split("/")[2] if path.startswith("/sp/") else ""
        for field in body:
            if field.endswith("IdFilter") and field not in ("campaignIdFilter", "adGroupIdFilter") \
                    and field != allowed_filters.get(resource):
                return httpx.Response(400, json={"message": f"zły filtr {field} dla {resource}"})
        if state["fail_path"] == path:
            return httpx.Response(500, json={"message": "awaria"})
        if state["item_error"] == path:
            key = next(iter(body))
            return httpx.Response(207, json={key: {"success": [], "error": [{"index": 0, "errors": ["zła stawka"]}]}})
        if path == "/v2/profiles":
            return httpx.Response(200, json=[
                {"profileId": 111, "countryCode": "DE", "currencyCode": "EUR", "accountInfo": {"type": "seller"}},
                {"profileId": 333, "countryCode": "FR", "currencyCode": "EUR", "accountInfo": {"type": "seller"}},
                {"profileId": 444, "countryCode": "PL", "currencyCode": "PLN", "accountInfo": {"type": "seller"}}])
        if path == "/sp/keywords/list":
            wanted = (body.get("keywordIdFilter") or {}).get("include")
            return httpx.Response(200, json={"keywords": [k for k in [KEYWORD] if not wanted or k["keywordId"] in wanted]})
        if path == "/sp/targets/list":
            return httpx.Response(200, json={"targetingClauses": [
                {"targetId": "t1", "expression": [{"type": "ASIN_SAME_AS", "value": "B0EXIST"}],
                 "bid": 0.4, "state": "ENABLED"}]})
        if path == "/sp/negativeKeywords/list":
            neg = [{"keywordId": "n1", "keywordText": "Zubehör", "matchType": "NEGATIVE_EXACT", "state": "ENABLED"}]
            wanted = (body.get("negativeKeywordIdFilter") or {}).get("include")
            return httpx.Response(200, json={"negativeKeywords": [n for n in neg if not wanted or n["keywordId"] in wanted]})
        if path in ("/sp/negativeTargets/list", "/sp/campaignNegativeKeywords/list",
                    "/sp/campaignNegativeTargets/list"):
            return httpx.Response(200, json={})
        if path == "/sp/campaigns/list":
            return httpx.Response(200, json={"campaigns": [CAMPAIGN]})
        if request.method in ("PUT", "POST"):
            key = next(iter(body))
            items = body[key] if isinstance(body[key], list) else body[key]["include"]
            return ok(key if isinstance(body[key], list) else path.split("/")[2], items)
        return httpx.Response(404, json={"message": f"nieobsłużone {request.method} {path}"})

    transport = httpx.MockTransport(handler)
    advertising._profiles_by_country.clear()
    advertising._currency_by_profile.clear()
    monkeypatch.setattr(advertising, "ads", AdsClient(LIVE, transport=transport))
    live = SPAPIClient(LIVE)
    monkeypatch.setattr(client_module.spapi, "cfg", live.cfg)
    monkeypatch.setattr(common.spapi, "cfg", live.cfg)
    seen.state = state
    return seen


class Seen(list):
    pass


def call(tool, args):
    result = asyncio.run(build_server().call_tool(tool, args))
    if getattr(result, "is_error", False):
        raise AssertionError(result.content[0].text)
    return json.loads(result.content[0].text)


def writes(seen):
    return [r for r in seen if r.method == "PUT" or (r.method == "POST" and not r.url.path.endswith("/list")
                                                    and r.url.path != "/auth/o2/token")]


def test_bids_preview_then_execute_with_log(api):
    preview = call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 0.65}]})
    assert preview["status"] == "preview"
    row = preview["request"]["changes"][0]
    assert (row["text"], row["bid_before"], row["bid_after"]) == ("hundebett", 0.5, 0.65)
    assert writes(api) == []

    done = call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 0.65}], "confirm": True})
    put = writes(api)[-1]
    assert put.method == "PUT" and put.url.path == "/sp/keywords"
    assert put.headers["Content-Type"] == "application/vnd.spKeyword.v3+json"
    assert json.loads(put.content) == {"keywords": [{"keywordId": "k1", "bid": 0.65}]}
    assert done["payload"]["success"] == {"keywords": 1}

    log = call("list_ad_changes", {})
    assert log["changes"][0]["action"] == "update_ad_bids"
    assert log["changes"][0]["items"][0]["bid_before"] == 0.5


def test_bids_warn_and_validate(api):
    preview = call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 1.5}]})
    assert "ponad 2×" in preview["request"]["changes"][0]["warning"]
    with pytest.raises(ToolError, match="poniżej minimum 0.02 EUR"):
        call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 0.01}]})
    with pytest.raises(ToolError, match="ENABLED albo PAUSED"):
        call("update_ad_bids", {"changes": [{"target_id": "t1", "state": "ARCHIVED"}]})


def test_country_uses_other_profile(api):
    call("update_ad_bids", {"changes": [{"keyword_id": "k1", "state": "paused"}], "country": "FR",
                            "confirm": True})
    put = writes(api)[-1]
    assert put.headers["Amazon-Advertising-API-Scope"] == "333"
    assert json.loads(put.content) == {"keywords": [{"keywordId": "k1", "state": "PAUSED"}]}


def test_negatives_skip_duplicates_ad_group_level(api):
    preview = call("add_ad_negatives", {"campaign_id": "c1", "ad_group_id": "g1",
                                        "keywords": ["zubehör", "katzenbett"], "asins": ["b0new"]})
    req = preview["request"]
    assert req["keywords"] == ["katzenbett"] and req["skipped_duplicates"] == ["zubehör"]
    assert req["asins"] == ["B0NEW"] and req["level"] == "ad_group"

    call("add_ad_negatives", {"campaign_id": "c1", "ad_group_id": "g1", "keywords": ["zubehör", "katzenbett"],
                              "asins": ["b0new"], "confirm": True})
    posted = {r.url.path: json.loads(r.content) for r in writes(api)}
    assert posted["/sp/negativeKeywords"]["negativeKeywords"] == [
        {"campaignId": "c1", "state": "ENABLED", "adGroupId": "g1", "keywordText": "katzenbett",
         "matchType": "NEGATIVE_EXACT"}]
    assert posted["/sp/negativeTargets"]["negativeTargetingClauses"][0]["expression"] == [
        {"type": "ASIN_SAME_AS", "value": "B0NEW"}]


def test_negatives_campaign_level_phrase(api):
    call("add_ad_negatives", {"campaign_id": "c1", "keywords": ["gebraucht"], "match_type": "negative_phrase",
                              "confirm": True})
    post = writes(api)[-1]
    assert post.url.path == "/sp/campaignNegativeKeywords"
    assert json.loads(post.content)["campaignNegativeKeywords"][0]["matchType"] == "NEGATIVE_PHRASE"


def test_remove_negatives(api):
    call("remove_ad_negatives", {"negative_ids": ["n1"], "confirm": True})
    post = writes(api)[-1]
    assert post.url.path == "/sp/negativeKeywords/delete"
    assert json.loads(post.content) == {"negativeKeywordIdFilter": {"include": ["n1"]}}


def test_add_keywords_harvest(api):
    preview = call("add_ad_keywords", {"campaign_id": "c1", "ad_group_id": "g1",
                                       "keywords": [{"text": "Hundebett", "match_type": "exact", "bid": 0.7},
                                                    {"text": "hundebett xxl", "match_type": "EXACT", "bid": 0.9}],
                                       "asins": [{"asin": "B0EXIST"}, {"asin": "B0NEU", "bid": 0.3}]})
    req = preview["request"]
    assert [k["text"] for k in req["keywords"]] == ["hundebett xxl"]
    assert [a["asin"] for a in req["asins"]] == ["B0NEU"]
    assert sorted(req["skipped_duplicates"]) == ["B0EXIST", "Hundebett [EXACT]"]

    call("add_ad_keywords", {"campaign_id": "c1", "ad_group_id": "g1",
                             "keywords": [{"text": "hundebett xxl", "match_type": "EXACT", "bid": 0.9}],
                             "confirm": True})
    post = writes(api)[-1]
    assert post.url.path == "/sp/keywords"
    assert json.loads(post.content)["keywords"][0] == {"campaignId": "c1", "adGroupId": "g1", "state": "ENABLED",
                                                       "keywordText": "hundebett xxl", "matchType": "EXACT",
                                                       "bid": 0.9}


def test_placements_merge(api):
    preview = call("update_ad_placements", {"campaign_id": "c1", "top_of_search": 50})
    assert preview["request"]["before"] == {"PLACEMENT_TOP": 20, "PLACEMENT_PRODUCT_PAGE": 0}
    assert preview["request"]["after"] == {"PLACEMENT_TOP": 50, "PLACEMENT_PRODUCT_PAGE": 0}

    call("update_ad_placements", {"campaign_id": "c1", "top_of_search": 50, "confirm": True})
    body = json.loads(writes(api)[-1].content)
    assert body == {"campaigns": [{"campaignId": "c1", "dynamicBidding": {
        "placementBidding": [{"placement": "PLACEMENT_TOP", "percentage": 50},
                             {"placement": "PLACEMENT_PRODUCT_PAGE", "percentage": 0}],
        "strategy": "LEGACY_FOR_SALES"}}]}
    with pytest.raises(ToolError, match="0–900"):
        call("update_ad_placements", {"campaign_id": "c1", "product_page": 1000})


def test_report_options_passed(monkeypatch):
    import amazon_mcp.tools.reports as reports

    captured = {}
    monkeypatch.setattr(reports.spapi, "call", lambda *a, **kw: captured.update(kw) or {"mode": "mock"})
    call("create_report", {"report_type": "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT",
                           "report_options": {"reportPeriod": "WEEK", "asin": "B0A B0B"}})
    assert captured["reportOptions"] == {"reportPeriod": "WEEK", "asin": "B0A B0B"}


def test_remove_unknown_negative_blocked(api):
    with pytest.raises(ToolError, match="nie istnieją"):
        call("remove_ad_negatives", {"negative_ids": ["n999"]})
    assert writes(api) == []


def test_bid_safety_cap_and_jump(api):
    with pytest.raises(ToolError, match="powyżej bezpiecznika 5"):
        call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 45}]})
    with pytest.raises(ToolError, match="ponad 3× obecnej"):
        call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 1.6}]})
    ok = call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 1.6}], "allow_big_change": True})
    assert ok["status"] == "preview" and ok["request"]["changes"][0]["currency"] == "EUR"
    with pytest.raises(ToolError, match="powyżej bezpiecznika"):
        call("add_ad_keywords", {"campaign_id": "c1", "ad_group_id": "g1",
                                 "keywords": [{"text": "neu", "match_type": "EXACT", "bid": 45}]})


def test_bid_cap_in_profile_currency(api):
    preview = call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 1.2}], "country": "PL"})
    assert preview["request"]["changes"][0]["currency"] == "PLN"


def test_unknown_id_blocks_write(api):
    with pytest.raises(ToolError, match="ID nie istnieją"):
        call("update_ad_bids", {"changes": [{"keyword_id": "k999", "bid": 0.5}]})
    assert writes(api) == []


def test_item_errors_give_failed_status_and_log(api):
    api.state["item_error"] = "/sp/keywords"
    r = call("update_ad_bids", {"changes": [{"keyword_id": "k1", "bid": 0.6}], "confirm": True})
    assert r["status"] == "failed" and r["payload"]["errors"]
    assert call("list_ad_changes", {})["changes"][0]["result"]["status"] == "failed"


def test_exception_midway_is_logged_as_partial(api):
    api.state["fail_path"] = "/sp/targets"
    r = call("add_ad_keywords", {"campaign_id": "c1", "ad_group_id": "g1",
                                 "keywords": [{"text": "neu", "match_type": "EXACT", "bid": 0.5}],
                                 "asins": [{"asin": "B0NEU", "bid": 0.3}], "confirm": True})
    assert r["status"] == "partial"
    assert r["payload"]["success"] == {"keywords": 1}
    assert "awaria" in r["payload"]["errors"][0]["exception"]
    entry = call("list_ad_changes", {})["changes"][0]
    assert entry["action"] == "add_ad_keywords" and entry["profile_id"] == "111"


def test_placements_keep_shopper_cohorts(api, monkeypatch):
    cohorts = [{"percentage": 30, "shopperCohortType": "AUDIENCE_SEGMENT", "audienceSegments": []}]
    monkeypatch.setitem(CAMPAIGN["dynamicBidding"], "shopperCohortBidding", cohorts)
    call("update_ad_placements", {"campaign_id": "c1", "product_page": 10, "confirm": True})
    body = json.loads(writes(api)[-1].content)
    assert body["campaigns"][0]["dynamicBidding"]["shopperCohortBidding"] == cohorts


def test_change_log_limit_and_broken_lines(api, tmp_path):
    from amazon_mcp import ads_log
    path = ads_log.log_path()
    path.write_text('{"action": "a"}\nnie-json\n{"action": "b"}\n', encoding="utf-8")
    assert call("list_ad_changes", {"limit": 1})["changes"] == [{"action": "b"}]
    assert len(call("list_ad_changes", {"limit": 0})["changes"]) == 3  # 0 = domyślne 50, nie „cały plik”
    changes = call("list_ad_changes", {"limit": 5})["changes"]
    assert changes[1] == {"broken_line": "nie-json"} and len(changes) == 3

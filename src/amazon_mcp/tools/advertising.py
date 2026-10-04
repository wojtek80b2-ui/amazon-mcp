"""Amazon Advertising API (Sponsored Products).

Uwaga: reklamy to OSOBNE API (advertising-api*.amazon.com), nie część SP-API.
Wymaga osobnych kluczy ADS_API_* w .env; refresh token i profil ustawia
`python -m amazon_mcp.ads_auth`.
"""

from __future__ import annotations

import gzip
import json

import httpx

from amazon_mcp import mock_data
from amazon_mcp.ads_client import SP_CAMPAIGN_MEDIA_TYPE, ads
from amazon_mcp.client import AmazonAPIError, spapi
from amazon_mcp.tools._common import READ_ONLY, WRITE, guarded_write

REPORT_MEDIA_TYPE = "application/vnd.createasyncreportrequest.v3+json"

# Gotowe zestawy raportów Sponsored Products (Reporting API v3).
REPORTS = {
    "campaigns": {"reportTypeId": "spCampaigns", "groupBy": ["campaign"],
                  "columns": ["campaignId", "campaignName", "campaignStatus", "campaignBudgetAmount",
                              "impressions", "clicks", "cost", "sales7d", "purchases7d"]},
    "search_terms": {"reportTypeId": "spSearchTerm", "groupBy": ["searchTerm"],
                     "columns": ["campaignName", "adGroupName", "keyword", "matchType", "searchTerm",
                                 "impressions", "clicks", "cost", "sales7d", "purchases7d"]},
    "targeting": {"reportTypeId": "spTargeting", "groupBy": ["targeting"],
                  "columns": ["campaignName", "adGroupName", "targeting", "keywordType", "matchType",
                              "impressions", "clicks", "cost", "sales7d", "purchases7d"]},
    "products": {"reportTypeId": "spAdvertisedProduct", "groupBy": ["advertiser"],
                 "columns": ["campaignName", "adGroupName", "advertisedAsin", "advertisedSku",
                             "impressions", "clicks", "cost", "sales7d", "purchases7d"]},
}


def _live() -> bool:
    return not spapi.cfg.is_mock


def _with_acos(rows: list[dict]) -> list[dict]:
    for row in rows:
        sales = row.get("sales7d") or 0
        row["acos"] = round(100 * (row.get("cost") or 0) / sales, 1) if sales else None
    return rows


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def list_ad_profiles() -> dict:
        """Profile reklamowe (konto Ads w każdym kraju) z profileId. Działa bez ustawionego ADS_API_PROFILE_ID."""
        if not _live():
            return {"mode": "mock", "payload": mock_data.AD_PROFILES}
        return {"mode": "live", "payload": ads.request("GET", "/v2/profiles", profile_scope=False)}

    @mcp.tool(annotations=READ_ONLY)
    def list_ad_campaigns(state: str | None = None, next_token: str | None = None) -> dict:
        """Kampanie Sponsored Products (nazwa, stan, budżet, targetowanie).

        state: ENABLED, PAUSED, ARCHIVED. Wyniki (kliknięcia, koszt, ACoS) w trybie live daje
        request_ad_report(report="campaigns").
        """
        if not _live():
            campaigns = [c for c in mock_data.AD_CAMPAIGNS if not state or c["state"] == state.upper()]
            return {"mode": "mock", "payload": {"campaigns": campaigns}}
        body: dict = {"maxResults": 100}
        if state:
            body["stateFilter"] = {"include": [state.upper()]}
        if next_token:
            body["nextToken"] = next_token
        data = ads.request("POST", "/sp/campaigns/list", json=body, media_type=SP_CAMPAIGN_MEDIA_TYPE)
        result = {"mode": "live", "payload": {"campaigns": data.get("campaigns", [])}}
        if data.get("nextToken"):
            result["next_token"] = data["nextToken"]
        return result

    @mcp.tool(annotations=WRITE)
    def update_ad_campaign(
        campaign_id: str,
        state: str | None = None,
        daily_budget: float | None = None,
        confirm: bool = False,
    ) -> dict:
        """Zmień stan (ENABLED/PAUSED) lub dzienny budżet kampanii. Bez confirm=true tylko podgląd."""
        changes: dict = {"campaignId": campaign_id}
        if state:
            changes["state"] = state.upper()
        if daily_budget is not None:
            changes["budget"] = {"budget": daily_budget, "budgetType": "DAILY"}

        def execute():
            if not _live():
                return {"mode": "mock", "payload": {"code": "SUCCESS", **changes}}
            data = ads.request("PUT", "/sp/campaigns", json={"campaigns": [changes]},
                               media_type=SP_CAMPAIGN_MEDIA_TYPE)
            errors = (data.get("campaigns") or {}).get("error") or []
            if errors:
                raise AmazonAPIError(f"Ads API odrzuciło zmianę: {errors}")
            return {"mode": "live", "payload": data}

        return guarded_write(confirm, f"Zmiana kampanii {campaign_id}", changes, execute)

    @mcp.tool(annotations=READ_ONLY)
    def request_ad_report(start_date: str, end_date: str, report: str = "campaigns") -> dict:
        """Zamów raport wyników Sponsored Products (wyświetlenia, kliknięcia, koszt, sprzedaż 7d).

        report: campaigns, search_terms, targeting, products. Daty YYYY-MM-DD (maks. 31 dni, do 95 dni wstecz).
        Raport generuje się asynchronicznie: zwraca report_id do get_ad_report.
        """
        if report not in REPORTS:
            raise AmazonAPIError(f"Nieznany raport '{report}'. Dostępne: {', '.join(REPORTS)}")
        if not _live():
            return {"mode": "mock", "payload": {"reportId": "mock-report-1", "status": "PENDING"}}
        spec = REPORTS[report]
        body = {
            "name": f"amazon-mcp {report} {start_date}..{end_date}",
            "startDate": start_date,
            "endDate": end_date,
            "configuration": {"adProduct": "SPONSORED_PRODUCTS", "groupBy": spec["groupBy"],
                              "columns": spec["columns"], "reportTypeId": spec["reportTypeId"],
                              "timeUnit": "SUMMARY", "format": "GZIP_JSON"},
        }
        return {"mode": "live", "payload": ads.request("POST", "/reporting/reports", json=body,
                                                        media_type=REPORT_MEDIA_TYPE)}

    @mcp.tool(annotations=READ_ONLY)
    def get_ad_report(report_id: str, max_rows: int = 200) -> dict:
        """Status i wiersze raportu z request_ad_report (z wyliczonym ACoS %). Gdy status PENDING, spróbuj za chwilę."""
        if not _live():
            rows = [{"campaignName": c["name"], "impressions": c["metrics"]["impressions"],
                     "clicks": c["metrics"]["clicks"], "cost": c["metrics"]["cost"],
                     "sales7d": c["metrics"]["sales"]} for c in mock_data.AD_CAMPAIGNS]
            return {"mode": "mock", "payload": {"status": "COMPLETED", "rows": _with_acos(rows)}}
        meta = ads.request("GET", f"/reporting/reports/{report_id}")
        if meta.get("status") != "COMPLETED" or not meta.get("url"):
            return {"mode": "live", "payload": meta}
        raw = httpx.get(meta["url"], timeout=60).content
        rows = json.loads(gzip.decompress(raw))
        return {"mode": "live", "payload": {"status": "COMPLETED", "total_rows": len(rows),
                                            "rows": _with_acos(rows[:max_rows])}}

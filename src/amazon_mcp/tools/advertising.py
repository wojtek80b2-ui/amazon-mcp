"""Amazon Advertising API (Sponsored Products).

Uwaga: reklamy to OSOBNE API (advertising-api*.amazon.com), nie część SP-API.
Wymaga osobnych kluczy ADS_API_* w .env; refresh token i profil ustawia
`python -m amazon_mcp.ads_auth`.
"""

from __future__ import annotations

import gzip
import json

import httpx

from amazon_mcp import ads_log, mock_data
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
    # Podział na miejsca wyświetlania (góra wyszukiwania / reszta wyszukiwania / strona produktu).
    "placements": {"reportTypeId": "spCampaigns", "groupBy": ["campaign", "campaignPlacement"],
                   "columns": ["campaignId", "campaignName", "placementClassification",
                               "impressions", "clicks", "cost", "sales7d", "purchases7d"]},
}

TIME_UNITS = ("SUMMARY", "DAILY")

# Pamięć podręczna z /v2/profiles (tylko tryb live): kod kraju -> profileId, profileId -> waluta.
_profiles_by_country: dict[str, str] = {}
_currency_by_profile: dict[str, str] = {}


def _load_profiles() -> None:
    if _profiles_by_country:
        return
    for prof in ads.request("GET", "/v2/profiles", profile_scope=False):
        pid = str(prof["profileId"])
        _currency_by_profile[pid] = str(prof.get("currencyCode") or "")
        cc = str(prof.get("countryCode", "")).upper()
        is_seller = (prof.get("accountInfo") or {}).get("type", "seller") == "seller"
        if cc and (is_seller or cc not in _profiles_by_country):  # seller ma pierwszeństwo przed vendor
            _profiles_by_country[cc] = pid


def profile_currency(profile_id: str | None) -> str:
    """Waluta profilu (EUR, PLN, SEK, GBP, TRY...); pusty napis, gdy nieznana."""
    if not profile_id or not _live():
        return ""
    _load_profiles()
    return _currency_by_profile.get(str(profile_id), "")


def _live() -> bool:
    return not spapi.cfg.is_mock


def _profile(country: str | None) -> str | None:
    """Zamienia kod kraju (DE, PL, FR...) na profileId. Liczba przechodzi bez zmian. None = ADS_API_PROFILE_ID."""
    if not country:
        return None
    country = country.strip()
    if country.isdigit():
        return country
    code = country.upper()
    _load_profiles()
    if code not in _profiles_by_country:
        raise AmazonAPIError(f"Brak profilu reklamowego seller dla kraju '{code}'. "
                             f"Dostępne: {', '.join(sorted(_profiles_by_country))}")
    return _profiles_by_country[code]


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
    def list_ad_campaigns(state: str | None = None, next_token: str | None = None,
                          country: str | None = None) -> dict:
        """Kampanie Sponsored Products (nazwa, stan, budżet, targetowanie).

        state: ENABLED, PAUSED, ARCHIVED. country: kod kraju (DE, PL, FR, IT, ES, NL, SE, UK, TR)
        albo profileId; bez niego domyślny profil z .env. Wyniki (kliknięcia, koszt, ACoS) w trybie
        live daje request_ad_report(report="campaigns").
        """
        if not _live():
            campaigns = [c for c in mock_data.AD_CAMPAIGNS if not state or c["state"] == state.upper()]
            return {"mode": "mock", "payload": {"campaigns": campaigns}}
        body: dict = {"maxResults": 100}
        if state:
            body["stateFilter"] = {"include": [state.upper()]}
        if next_token:
            body["nextToken"] = next_token
        data = ads.request("POST", "/sp/campaigns/list", json=body, media_type=SP_CAMPAIGN_MEDIA_TYPE,
                           profile_id=_profile(country))
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
        country: str | None = None,
    ) -> dict:
        """Zmień stan (ENABLED/PAUSED) lub dzienny budżet kampanii. Bez confirm=true tylko podgląd.

        country: kod kraju albo profileId kampanii (domyślnie profil z .env).
        """
        changes: dict = {"campaignId": campaign_id}
        if state:
            changes["state"] = state.upper()
        if daily_budget is not None:
            changes["budget"] = {"budget": daily_budget, "budgetType": "DAILY"}

        def execute():
            if not _live():
                return {"mode": "mock", "payload": {"code": "SUCCESS", **changes}}
            profile_id = _profile(country)
            data = ads.request("PUT", "/sp/campaigns", json={"campaigns": [changes]},
                               media_type=SP_CAMPAIGN_MEDIA_TYPE, profile_id=profile_id)
            errors = (data.get("campaigns") or {}).get("error") or []
            log = ads_log.log_change("update_ad_campaign", profile_id, [changes], {"errors": errors})
            if errors:
                raise AmazonAPIError(f"Ads API odrzuciło zmianę: {errors}")
            return {"mode": "live", "payload": data, "change_log": log}

        return guarded_write(confirm, f"Zmiana kampanii {campaign_id}", changes, execute)

    @mcp.tool(annotations=READ_ONLY)
    def request_ad_report(start_date: str, end_date: str, report: str = "campaigns",
                          time_unit: str = "SUMMARY", country: str | None = None) -> dict:
        """Zamów raport wyników Sponsored Products (wyświetlenia, kliknięcia, koszt, sprzedaż 7d).

        report: campaigns, search_terms, targeting, products, placements (kampania x miejsce wyświetlania:
        góra wyszukiwania / reszta wyszukiwania / strona produktu).
        time_unit: SUMMARY (suma za okres) albo DAILY (wiersz na dzień, kolumna date).
        country: kod kraju (DE, PL, FR...) albo profileId; domyślnie profil z .env. Ten sam country
        podaj potem w get_ad_report.
        Daty YYYY-MM-DD (maks. 31 dni, do 95 dni wstecz). Raport generuje się asynchronicznie:
        zwraca report_id do get_ad_report.
        """
        if report not in REPORTS:
            raise AmazonAPIError(f"Nieznany raport '{report}'. Dostępne: {', '.join(REPORTS)}")
        time_unit = time_unit.upper()
        if time_unit not in TIME_UNITS:
            raise AmazonAPIError(f"Nieznany time_unit '{time_unit}'. Dostępne: {', '.join(TIME_UNITS)}")
        if not _live():
            return {"mode": "mock", "payload": {"reportId": "mock-report-1", "status": "PENDING"}}
        spec = REPORTS[report]
        columns = list(spec["columns"])
        if time_unit == "DAILY":
            columns = ["date", *columns]  # Amazon wymaga kolumny date przy DAILY
        body = {
            "name": f"amazon-mcp {report} {time_unit} {start_date}..{end_date}",
            "startDate": start_date,
            "endDate": end_date,
            "configuration": {"adProduct": "SPONSORED_PRODUCTS", "groupBy": spec["groupBy"],
                              "columns": columns, "reportTypeId": spec["reportTypeId"],
                              "timeUnit": time_unit, "format": "GZIP_JSON"},
        }
        return {"mode": "live", "payload": ads.request("POST", "/reporting/reports", json=body,
                                                        media_type=REPORT_MEDIA_TYPE,
                                                        profile_id=_profile(country))}

    @mcp.tool(annotations=READ_ONLY)
    def get_ad_report(report_id: str, max_rows: int = 200, country: str | None = None) -> dict:
        """Status i wiersze raportu z request_ad_report (z wyliczonym ACoS %). Gdy status PENDING, spróbuj za chwilę.

        country: ten sam kod kraju / profileId, który podano w request_ad_report.
        """
        if not _live():
            rows = [{"campaignName": c["name"], "impressions": c["metrics"]["impressions"],
                     "clicks": c["metrics"]["clicks"], "cost": c["metrics"]["cost"],
                     "sales7d": c["metrics"]["sales"]} for c in mock_data.AD_CAMPAIGNS]
            return {"mode": "mock", "payload": {"status": "COMPLETED", "rows": _with_acos(rows)}}
        meta = ads.request("GET", f"/reporting/reports/{report_id}", profile_id=_profile(country))
        if meta.get("status") != "COMPLETED" or not meta.get("url"):
            return {"mode": "live", "payload": meta}
        raw = httpx.get(meta["url"], timeout=60).content
        rows = json.loads(gzip.decompress(raw))
        return {"mode": "live", "payload": {"status": "COMPLETED", "total_rows": len(rows),
                                            "rows": _with_acos(rows[:max_rows])}}

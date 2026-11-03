"""Klient Amazon Advertising API (osobne API, nie część SP-API).

Logowanie: LWA refresh token -> access token (ważny ~1 h, odświeżany automatycznie).
Każde zapytanie wysyła nagłówki Amazon-Advertising-API-ClientId oraz
Amazon-Advertising-API-Scope (= profile ID, czyli konto reklamowe w danym kraju).
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from amazon_mcp.client import AmazonAPIError
from amazon_mcp.config import Settings, settings as default_settings

REGIONS = {
    "NA": {"api": "https://advertising-api.amazon.com", "token": "https://api.amazon.com/auth/o2/token",
           "consent": "https://www.amazon.com/ap/oa"},
    "EU": {"api": "https://advertising-api-eu.amazon.com", "token": "https://api.amazon.co.uk/auth/o2/token",
           "consent": "https://eu.account.amazon.com/ap/oa"},
    "FE": {"api": "https://advertising-api-fe.amazon.com", "token": "https://api.amazon.co.jp/auth/o2/token",
           "consent": "https://apac.account.amazon.com/ap/oa"},
}

SCOPE = "advertising::campaign_management"
SP_CAMPAIGN_MEDIA_TYPE = "application/vnd.spCampaign.v3+json"


class AdsClient:
    def __init__(self, cfg: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.cfg = cfg or default_settings
        self._transport = transport
        self._token: str | None = None
        self._token_expires = 0.0

    @property
    def region(self) -> dict[str, str]:
        try:
            return REGIONS[self.cfg.ads_region]
        except KeyError as exc:
            raise AmazonAPIError(f"Nieznany ADS_API_REGION '{self.cfg.ads_region}'. Dostępne: NA, EU, FE") from exc

    def missing_credentials(self, need_profile: bool = True) -> list[str]:
        required = {
            "ADS_API_CLIENT_ID": self.cfg.ads_client_id,
            "ADS_API_CLIENT_SECRET": self.cfg.ads_client_secret,
            "ADS_API_REFRESH_TOKEN": self.cfg.ads_refresh_token,
        }
        if need_profile:
            required["ADS_API_PROFILE_ID"] = self.cfg.ads_profile_id
        return [name for name, value in required.items() if not value]

    def _http(self) -> httpx.Client:
        return httpx.Client(timeout=30, transport=self._transport)

    def access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        with self._http() as http:
            resp = http.post(self.region["token"], data={
                "grant_type": "refresh_token",
                "refresh_token": self.cfg.ads_refresh_token,
                "client_id": self.cfg.ads_client_id,
                "client_secret": self.cfg.ads_client_secret,
            })
        if resp.status_code != 200:
            raise AmazonAPIError(f"Ads API: nie udało się odświeżyć tokena LWA ({resp.status_code}): {resp.text}")
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def request(self, method: str, path: str, *, json: Any = None, params: dict | None = None,
                media_type: str | None = None, profile_scope: bool = True) -> Any:
        missing = self.missing_credentials(need_profile=profile_scope)
        if missing:
            raise AmazonAPIError("Ads API: brakuje w .env: " + ", ".join(missing))

        headers = {
            "Authorization": f"Bearer {self.access_token()}",
            "Amazon-Advertising-API-ClientId": self.cfg.ads_client_id,
        }
        if profile_scope:
            headers["Amazon-Advertising-API-Scope"] = self.cfg.ads_profile_id
        if media_type:
            headers["Content-Type"] = media_type
            headers["Accept"] = media_type
        with self._http() as http:
            resp = http.request(method, self.region["api"] + path, headers=headers, json=json, params=params)
        if resp.status_code >= 400:
            raise AmazonAPIError(f"Ads API {method} {path} ({resp.status_code}): {resp.text}")
        return resp.json() if resp.content else None


ads = AdsClient()

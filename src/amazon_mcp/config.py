"""Konfiguracja wczytywana ze zmiennych środowiskowych / pliku .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# .env w katalogu projektu (dwa poziomy nad src/amazon_mcp) albo w bieżącym katalogu.
_PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_PROJECT_ENV)
load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mode: str = field(default_factory=lambda: _env("AMAZON_MODE", "mock").lower())
    lwa_client_id: str = field(default_factory=lambda: _env("SP_API_LWA_CLIENT_ID"))
    lwa_client_secret: str = field(default_factory=lambda: _env("SP_API_LWA_CLIENT_SECRET"))
    refresh_token: str = field(default_factory=lambda: _env("SP_API_REFRESH_TOKEN"))
    seller_id: str = field(default_factory=lambda: _env("SP_API_SELLER_ID"))
    marketplace: str = field(default_factory=lambda: _env("SP_API_MARKETPLACE", "PL").upper())
    ads_client_id: str = field(default_factory=lambda: _env("ADS_API_CLIENT_ID"))
    ads_client_secret: str = field(default_factory=lambda: _env("ADS_API_CLIENT_SECRET"))
    ads_refresh_token: str = field(default_factory=lambda: _env("ADS_API_REFRESH_TOKEN"))
    ads_profile_id: str = field(default_factory=lambda: _env("ADS_API_PROFILE_ID"))
    ads_region: str = field(default_factory=lambda: _env("ADS_API_REGION", "EU").upper())
    allow_writes: bool = field(
        default_factory=lambda: _env("AMAZON_ALLOW_WRITES", "true").lower() in ("1", "true", "yes")
    )

    @property
    def is_mock(self) -> bool:
        return self.mode != "live"

    @property
    def sp_api_credentials(self) -> dict[str, str]:
        return {
            "lwa_app_id": self.lwa_client_id,
            "lwa_client_secret": self.lwa_client_secret,
            "refresh_token": self.refresh_token,
        }

    def missing_sp_api_credentials(self) -> list[str]:
        required = {
            "SP_API_LWA_CLIENT_ID": self.lwa_client_id,
            "SP_API_LWA_CLIENT_SECRET": self.lwa_client_secret,
            "SP_API_REFRESH_TOKEN": self.refresh_token,
        }
        return [name for name, value in required.items() if not value]


settings = Settings()

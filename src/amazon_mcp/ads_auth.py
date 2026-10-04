"""Jednorazowa konfiguracja Amazon Ads API: refresh token + wybór profilu.

Uruchom:  python -m amazon_mcp.ads_auth

Wymaga w .env: ADS_API_CLIENT_ID, ADS_API_CLIENT_SECRET (z Security Profile w konsoli
Login with Amazon) oraz ADS_API_REGION. Skrypt:
1. pokazuje link do zgody Amazon (logujesz się kontem, które ma dostęp do reklam),
2. zamienia kod z przekierowania na refresh token,
3. pobiera listę profili reklamowych (kraje) i zapisuje wybrany do .env.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from amazon_mcp.ads_client import REGIONS, SCOPE, AdsClient
from amazon_mcp.config import _PROJECT_ENV, settings


def set_env_value(path: Path, key: str, value: str) -> None:
    """Wpisz KEY=value do pliku .env (podmienia istniejącą linię albo dopisuje na końcu)."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda _: line, text)
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
    path.write_text(text, encoding="utf-8")


def consent_url(client_id: str, region: str, redirect_uri: str) -> str:
    query = urlencode({"client_id": client_id, "scope": SCOPE, "response_type": "code",
                       "redirect_uri": redirect_uri})
    return f"{REGIONS[region]['consent']}?{query}"


def extract_code(answer: str) -> str:
    """Przyjmuje sam kod albo cały adres z paska przeglądarki (…?code=XYZ&scope=…)."""
    answer = answer.strip()
    if "code=" in answer:
        return parse_qs(urlparse(answer).query).get("code", [answer])[0]
    return answer


def exchange_code(client_id: str, client_secret: str, region: str, code: str, redirect_uri: str) -> str:
    resp = httpx.post(REGIONS[region]["token"], timeout=30, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "client_secret": client_secret,
    })
    if resp.status_code != 200:
        raise SystemExit(f"Błąd wymiany kodu ({resp.status_code}): {resp.text}\n"
                         "Kod jest ważny tylko 5 minut i działa raz; wygeneruj nowy i spróbuj ponownie.")
    return resp.json()["refresh_token"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Konfiguracja Amazon Ads API (refresh token + profil)")
    parser.add_argument("--redirect-uri", default="https://www.amazon.de",
                        help="Musi być identyczny z 'Allowed Return URLs' w Security Profile")
    parser.add_argument("--env", type=Path, default=_PROJECT_ENV, help="Ścieżka do pliku .env")
    args = parser.parse_args()

    cfg = settings
    region = cfg.ads_region
    if not cfg.ads_client_id or not cfg.ads_client_secret:
        raise SystemExit("Uzupełnij najpierw ADS_API_CLIENT_ID i ADS_API_CLIENT_SECRET w .env.")
    if region not in REGIONS:
        raise SystemExit(f"ADS_API_REGION musi być jednym z: {', '.join(REGIONS)}")

    refresh_token = cfg.ads_refresh_token
    if refresh_token and input("ADS_API_REFRESH_TOKEN już jest w .env. Wygenerować nowy? [t/N] ").lower() != "t":
        print("Używam istniejącego refresh tokena.")
    else:
        print("\n1) Otwórz ten link w przeglądarce, zaloguj się i kliknij 'Allow':\n")
        print("   " + consent_url(cfg.ads_client_id, region, args.redirect_uri))
        print("\n2) Przeglądarka przejdzie na stronę", args.redirect_uri,
              "z dopiskiem ?code=... w adresie. Skopiuj CAŁY adres z paska.\n")
        code = extract_code(input("Wklej adres (albo sam kod): "))
        refresh_token = exchange_code(cfg.ads_client_id, cfg.ads_client_secret, region, code, args.redirect_uri)
        set_env_value(args.env, "ADS_API_REFRESH_TOKEN", refresh_token)
        print(f"\nZapisano ADS_API_REFRESH_TOKEN do {args.env}")

    client = AdsClient(replace(cfg, ads_refresh_token=refresh_token))
    profiles = client.request("GET", "/v2/profiles", profile_scope=False) or []
    if not profiles:
        raise SystemExit("Brak profili reklamowych. Sprawdź, czy to konto ma aktywne Amazon Ads (Kampanie w Seller Central).")

    print("\nProfile reklamowe:")
    for i, p in enumerate(profiles, 1):
        info = p.get("accountInfo", {})
        print(f"  {i}. {p.get('countryCode')}  profileId={p.get('profileId')}  "
              f"{info.get('type', '')}  {info.get('name', '')}  {p.get('currencyCode', '')}")
    default = next((i for i, p in enumerate(profiles, 1) if p.get("countryCode") == "DE"), 1)
    choice = input(f"\nKtóry profil zapisać jako domyślny? [{default}] ").strip() or str(default)
    profile = profiles[int(choice) - 1]
    set_env_value(args.env, "ADS_API_PROFILE_ID", str(profile["profileId"]))
    print(f"Zapisano ADS_API_PROFILE_ID={profile['profileId']} ({profile.get('countryCode')}). "
          "Zrestartuj Claude Desktop, żeby serwer wczytał nowe dane.")


if __name__ == "__main__":
    main()

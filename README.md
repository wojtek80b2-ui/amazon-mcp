# amazon-mcp: serwer MCP dla Amazon Seller Central

Serwer MCP (Model Context Protocol), który daje Claude dostęp do Twojego konta sprzedawcy
Amazon przez Selling Partner API (SP-API). Działa lokalnie; bez kluczy Amazon uruchamia się
w trybie **mock** (dane testowe), więc możesz go podłączyć i przetestować już teraz.

## Jak to działa

MCP to otwarty protokół, przez który Claude (Desktop, Code) rozmawia z zewnętrznymi
narzędziami. Serwer to zwykły program w Pythonie, który:

1. startuje jako proces uruchamiany przez Claude (transport `stdio`) albo jako usługa HTTP na VPS (`streamable-http`),
2. ogłasza listę **narzędzi** (nazwa, opis, parametry wygenerowane z typów funkcji Pythona),
3. na prośbę Claude wywołuje narzędzie i zwraca wynik jako JSON.

```
Claude  ⇄  (MCP, JSON-RPC)  ⇄  amazon-mcp  ⇄  (HTTPS, LWA OAuth)  ⇄  Amazon SP-API
```

Wywołania Amazon obsługuje biblioteka [python-amazon-sp-api](https://github.com/saleweaver/python-amazon-sp-api)
(logowanie LWA, odświeżanie tokenów, limity). Serwer korzysta z oficjalnego
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) w wersji 2.x.

## Struktura

```
amazon-mcp/
├── .env.example            # szablon poświadczeń -> skopiuj jako .env
├── pyproject.toml
├── src/amazon_mcp/
│   ├── server.py           # punkt wejścia, instrukcje dla Claude
│   ├── config.py           # wczytywanie .env
│   ├── client.py           # jedno miejsce wywołań SP-API (mock albo live)
│   ├── mock_data.py        # dane testowe w formacie odpowiedzi SP-API
│   └── tools/              # jeden plik = jedna kategoria API
│       ├── orders.py  inventory.py  pricing.py  listings.py  catalog.py
│       ├── reports.py  finances.py  fees.py  feeds.py  sellers.py
│       └── advertising.py
└── tests/
```

## Narzędzia (28)

| Kategoria | Narzędzia | SP-API |
|---|---|---|
| Status | `server_status`, `get_marketplace_participation` | Sellers v1 |
| Zamówienia | `list_orders`, `get_order`, `get_order_items` | Orders v0 |
| Magazyn FBA | `get_fba_inventory` | FBA Inventory v1 |
| Ceny | `get_competitive_pricing`, `get_my_prices`, `get_item_offers`, `update_price`* | Product Pricing v0, Listings Items |
| Listingi | `search_listings`, `get_listing`, `update_listing`*, `create_listing`*, `delete_listing`* | Listings Items 2021-08-01 |
| Katalog | `search_catalog`, `get_catalog_item` | Catalog Items 2022-04-01 |
| Raporty | `list_reports`, `create_report`, `get_report`, `get_report_document` | Reports 2021-06-30 |
| Finanse | `list_financial_events`, `get_order_financial_events` | Finances v0 |
| Opłaty | `estimate_fees` | Product Fees v0 |
| Feedy | `list_feeds`, `get_feed` | Feeds 2021-06-30 |
| Reklamy | `list_ad_profiles`, `list_ad_campaigns`, `update_ad_campaign`*, `request_ad_report`, `get_ad_report` | Amazon Ads API: Sponsored Products v3, Reporting v3 |

\* Operacje zapisu. Bez `confirm=true` zwracają tylko **podgląd** tego, co zostałoby wysłane.
Claude jest poinstruowany, żeby najpierw pokazać podgląd i poczekać na Twoją zgodę.
`AMAZON_ALLOW_WRITES=false` w `.env` blokuje zapis całkowicie.

## Instalacja (lokalnie)

Wymagany Python 3.10+.

```bash
cd amazon-mcp
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env        # macOS/Linux: cp .env.example .env
pytest                        # 20 testów, wszystkie powinny przejść
```

### Podłączenie do Claude Desktop

Edytuj plik konfiguracyjny (Claude Desktop → Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "amazon-seller": {
      "command": "C:\\sciezka\\do\\amazon-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "amazon_mcp"]
    }
  }
}
```

Na macOS/Linux `command` to `/sciezka/do/amazon-mcp/.venv/bin/python`. Zrestartuj Claude Desktop
i zapytaj np. „Pokaż status serwera Amazon” albo „Jakie mam niewysłane zamówienia?”.

### Claude Code

```bash
claude mcp add amazon-seller -- /sciezka/do/amazon-mcp/.venv/bin/python -m amazon_mcp
```

### VPS (opcjonalnie, później)

```bash
python -m amazon_mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Endpoint: `http://host:8000/mcp`. Na VPS wystaw go tylko przez HTTPS (reverse proxy)
i z uwierzytelnianiem; ten serwer ma dostęp do Twojego konta sprzedawcy.

## Dodanie poświadczeń Amazon (gdy je będziesz mieć)

1. **Konto deweloperskie**: Seller Central → *Apps and Services* → *Develop Apps* → zarejestruj się
   jako deweloper (wybierz *private developer*, czyli aplikacja tylko dla własnego konta).
   Zaznacz role, których potrzebujesz (np. Product Listing, Pricing, Inventory and Order Tracking,
   Amazon Fulfillment, Finance and Accounting, Selling Partner Insights). Akceptacja trwa zwykle kilka dni.
2. **Aplikacja**: w *Develop Apps* kliknij *Add new app client*, typ API: *SP API*.
3. **Klucze LWA**: przy aplikacji kliknij *View* w kolumnie *LWA credentials*:
   skopiuj **Client identifier** i **Client secret**.
4. **Refresh token**: przy aplikacji *Authorize* → *Authorize app*. Skopiuj **refresh token**
   (zaczyna się od `Atzr|`).
5. **Seller ID**: Seller Central → *Settings* → *Account Info* → *Merchant Token*.
6. Uzupełnij `.env`:

   ```
   AMAZON_MODE=live
   SP_API_LWA_CLIENT_ID=amzn1.application-oa2-client....
   SP_API_LWA_CLIENT_SECRET=...
   SP_API_REFRESH_TOKEN=Atzr|...
   SP_API_SELLER_ID=A1...
   SP_API_MARKETPLACE=PL
   ```
7. Zrestartuj Claude i wywołaj `server_status`: `mode` powinno pokazać `live`,
   a `missing_sp_api_credentials` pustą listę.

Klucze AWS (IAM) nie są już potrzebne: Amazon od 2023 r. wymaga tylko LWA.
Plik `.env` jest w `.gitignore`; nigdy go nie commituj.

### Reklamy (Amazon Ads API)

Reklamy to osobne Amazon Ads API z osobną rejestracją i osobnymi kluczami:

1. W konsoli Login with Amazon (developer.amazon.com/loginwithamazon/console) utwórz
   **Security Profile**. W *Web Settings* dodaj **Allowed Return URL** `https://www.amazon.de`.
2. Złóż wniosek o dostęp na advertising.amazon.com/about-api (jako reklamodawca zarządzający
   własnymi kampaniami), podając Client ID z kroku 1. Poczekaj na mail z akceptacją.
3. Wpisz do `.env` `ADS_API_CLIENT_ID`, `ADS_API_CLIENT_SECRET` i `ADS_API_REGION=EU`.
4. Uruchom `python -m amazon_mcp.ads_auth`: skrypt da link do zgody, zamieni kod z przekierowania
   na refresh token, pokaże profile reklamowe (kraje) i zapisze `ADS_API_REFRESH_TOKEN`
   oraz `ADS_API_PROFILE_ID` do `.env`.
5. Zrestartuj Claude i wywołaj `server_status`: `missing_ads_api_credentials` powinno być puste.

`list_ad_campaigns` zwraca kampanie Sponsored Products; wyniki (kliknięcia, koszt, sprzedaż, ACoS)
dają `request_ad_report` + `get_ad_report`, bo Amazon generuje raporty asynchronicznie.

## Dodawanie kolejnych endpointów

Każde wywołanie przechodzi przez `spapi.call(klasa_api, metoda, ..., mock=dane_testowe)`.
Klasy i metody to te z `sp_api.api` (np. `OrdersV0.get_order_address`, `FulfillmentInboundV20240320.create_inbound_plan`,
`Notifications.create_subscription`). Przykład nowego narzędzia:

```python
@mcp.tool(annotations=READ_ONLY)
def get_order_address(order_id: str) -> dict:
    """Adres wysyłki zamówienia (dane PII, wymaga roli Direct-to-Consumer Shipping)."""
    return spapi.call("OrdersV0", "get_order_address", order_id, mock={"ShippingAddress": {...}})
```

Nowy plik w `tools/` dopisz do listy `MODULES` w `tools/__init__.py`.
Docstring funkcji to opis, który widzi Claude; typy parametrów stają się schematem narzędzia.

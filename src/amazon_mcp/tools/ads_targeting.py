"""Amazon Ads API: grupy reklam, słowa, targety, negatywy, placementy (Sponsored Products v3).

Odpowiednik akcji Scale Insights: reguły stawek, negacje (blacklista), import fraz do exact,
reguła placementów i dziennik zmian. Każdy zapis: najpierw podgląd ze stanem przed → po,
wykonanie dopiero z confirm=true, potem wpis w dzienniku (list_ad_changes).
"""

from __future__ import annotations

from typing import Any

from amazon_mcp import ads_log
from amazon_mcp.client import AmazonAPIError
from amazon_mcp.tools import advertising as adv
from amazon_mcp.tools._common import READ_ONLY, WRITE, guarded_write

MT = {
    "campaigns": "application/vnd.spCampaign.v3+json",
    "adGroups": "application/vnd.spAdGroup.v3+json",
    "keywords": "application/vnd.spKeyword.v3+json",
    "targets": "application/vnd.spTargetingClause.v3+json",
    "negativeKeywords": "application/vnd.spNegativeKeyword.v3+json",
    "campaignNegativeKeywords": "application/vnd.spCampaignNegativeKeyword.v3+json",
    "negativeTargets": "application/vnd.spNegativeTargetingClause.v3+json",
    "campaignNegativeTargets": "application/vnd.spCampaignNegativeTargetingClause.v3+json",
}
# Klucz listy w odpowiedzi Amazona dla każdego zasobu.
KEY = {
    "campaigns": "campaigns",
    "adGroups": "adGroups",
    "keywords": "keywords",
    "targets": "targetingClauses",
    "negativeKeywords": "negativeKeywords",
    "campaignNegativeKeywords": "campaignNegativeKeywords",
    "negativeTargets": "negativeTargetingClauses",
    "campaignNegativeTargets": "campaignNegativeTargetingClauses",
}
# Pole ID w obiektach danego zasobu (do filtrów i usuwania).
ID_FIELD = {
    "keywords": "keywordId", "negativeKeywords": "keywordId", "campaignNegativeKeywords": "keywordId",
    "targets": "targetId", "negativeTargets": "targetId", "campaignNegativeTargets": "targetId",
}
# Nazwa filtra ID przy /list i /delete. UWAGA: nieznany filtr Amazon ignoruje po cichu (zwraca wszystko),
# więc dla negatywów MUSZĄ być nazwy z prefiksem (sprawdzone na żywo 07.11.2026).
ID_FILTER = {
    "keywords": "keywordIdFilter", "targets": "targetIdFilter",
    "negativeKeywords": "negativeKeywordIdFilter", "campaignNegativeKeywords": "campaignNegativeKeywordIdFilter",
    "negativeTargets": "negativeTargetIdFilter", "campaignNegativeTargets": "campaignNegativeTargetIdFilter",
}
MAX_PAGES = 50
PLACEMENTS = {"top_of_search": "PLACEMENT_TOP", "product_page": "PLACEMENT_PRODUCT_PAGE",
              "rest_of_search": "PLACEMENT_REST_OF_SEARCH"}
MATCH_TYPES = ("EXACT", "PHRASE", "BROAD")
NEGATIVE_MATCH_TYPES = ("NEGATIVE_EXACT", "NEGATIVE_PHRASE")
MIN_BID_EUR = 0.02  # minimalna stawka SP na rynkach EUR (inne waluty sprawdza Amazon)
BID_JUMP_WARN = 2.0  # podgląd ostrzega, gdy nowa stawka > 2× obecnej
BID_JUMP_MAX = 3.0  # powyżej 3× obecnej stawki tylko z allow_big_change=true
# Bezpiecznik przed literówką (np. 45 zamiast 0,45): ok. 5 EUR w walucie profilu. To NIE jest limit Amazona.
MAX_BID = {"EUR": 5.0, "GBP": 5.0, "PLN": 25.0, "SEK": 60.0, "TRY": 200.0}
MAX_BID_DEFAULT = 5.0


def _negative_resource(level: str, kind: str) -> str:
    level, kind = level.lower(), kind.lower()
    if level not in ("ad_group", "campaign") or kind not in ("keywords", "products"):
        raise AmazonAPIError("level: ad_group albo campaign; kind: keywords albo products")
    if kind == "keywords":
        return "negativeKeywords" if level == "ad_group" else "campaignNegativeKeywords"
    return "negativeTargets" if level == "ad_group" else "campaignNegativeTargets"


def _list(resource: str, profile_id: str | None, *, campaign_id: str | None = None,
          ad_group_id: str | None = None, ids: list[str] | None = None, state: str | None = None,
          next_token: str | None = None, fetch_all: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {"maxResults": 100}
    if campaign_id:
        body["campaignIdFilter"] = {"include": [str(campaign_id)]}
    if ad_group_id:
        body["adGroupIdFilter"] = {"include": [str(ad_group_id)]}
    if ids:
        body[ID_FILTER[resource]] = {"include": [str(i) for i in ids]}
    if state:
        body["stateFilter"] = {"include": [state.upper()]}
    if next_token:
        body["nextToken"] = next_token
    items: list = []
    seen_tokens: set = set()
    for _ in range(MAX_PAGES):
        data = adv.ads.request("POST", f"/sp/{resource}/list", json=body, media_type=MT[resource],
                               profile_id=profile_id) or {}
        items.extend(data.get(KEY[resource], []))
        token = data.get("nextToken")
        if not (fetch_all and token) or token in seen_tokens:
            return {"items": items, "next_token": token}
        seen_tokens.add(token)
        body["nextToken"] = token
    raise AmazonAPIError(f"/sp/{resource}/list: ponad {MAX_PAGES} stron, zawęź filtr (kampania / grupa)")


def _errors(data: dict | None, resource: str) -> list:
    return ((data or {}).get(KEY[resource]) or {}).get("error") or []


def _successes(data: dict | None, resource: str) -> list:
    return ((data or {}).get(KEY[resource]) or {}).get("success") or []


def _pid(country: str | None) -> str | None:
    """profileId do zapytań i dziennika: z country albo domyślny ADS_API_PROFILE_ID."""
    if not adv._live():
        return None
    return adv._profile(country) or str(adv.ads.cfg.ads_profile_id)


def _check_bid(bid: Any, currency: str, current: Any = None, allow_big_change: bool = False) -> float:
    value = round(float(bid), 2)
    cap = MAX_BID.get(currency, MAX_BID_DEFAULT)
    if currency in ("", "EUR") and value < MIN_BID_EUR:
        raise AmazonAPIError(f"Stawka {value} poniżej minimum {MIN_BID_EUR} EUR")
    if value <= 0:
        raise AmazonAPIError(f"Stawka musi być dodatnia: {value}")
    if value > cap and not allow_big_change:
        raise AmazonAPIError(f"Stawka {value} {currency or 'EUR'} powyżej bezpiecznika {cap:g} — sprawdź przecinek; "
                             f"świadomie: allow_big_change=true")
    if current and value > BID_JUMP_MAX * float(current) and not allow_big_change:
        raise AmazonAPIError(f"Stawka {value} to ponad {BID_JUMP_MAX:g}× obecnej ({current}); świadomie: "
                             f"allow_big_change=true")
    return value


def _run_writes(action: str, profile_id: str | None, log_items: list[dict],
                calls: list[tuple[str, str, str, dict]]) -> dict:
    """Wykonuje zapisy po kolei. Dziennik powstaje ZAWSZE (także po wyjątku w połowie).

    calls: (metoda, zasób, ścieżka, body). Wynik: status executed / partial / failed.
    """
    outcome: dict[str, Any] = {"success": {}, "created": [], "errors": [], "not_sent": []}
    for i, (method, resource, path, body) in enumerate(calls):
        try:
            data = adv.ads.request(method, path, json=body, media_type=MT[resource], profile_id=profile_id)
        except Exception as exc:  # noqa: BLE001 - błąd sieci/API po części wysłanych zmian
            outcome["errors"].append({"resource": resource, "exception": str(exc)})
            outcome["not_sent"] = [c[1] for c in calls[i + 1:]]
            break
        ok = _successes(data, resource)
        outcome["success"][resource] = len(ok)
        outcome["created"] += [{"resource": resource, **s} for s in ok if isinstance(s, dict)]
        outcome["errors"] += [{"resource": resource, **e} if isinstance(e, dict) else {"resource": resource, "error": e}
                              for e in _errors(data, resource)]
    succeeded = sum(outcome["success"].values())
    status = "executed" if not outcome["errors"] else "partial" if succeeded else "failed"
    log = ads_log.log_change(action, profile_id, log_items, {"status": status, **outcome})
    return {"status": status, "mode": "live", "payload": outcome, "change_log": log}


def _mock_list(resource: str) -> dict:
    return {"mode": "mock", "payload": {resource: []}}


def register(mcp) -> None:
    # ------------------------------------------------------------------ odczyt
    @mcp.tool(annotations=READ_ONLY)
    def list_ad_groups(campaign_id: str | None = None, state: str | None = None,
                       country: str | None = None, next_token: str | None = None) -> dict:
        """Grupy reklam Sponsored Products (adGroupId, nazwa, stawka domyślna). country: DE, FR... albo profileId."""
        if not adv._live():
            return _mock_list("adGroups")
        res = _list("adGroups", adv._profile(country), campaign_id=campaign_id, state=state, next_token=next_token)
        return {"mode": "live", "payload": {"adGroups": res["items"]}, "next_token": res["next_token"]}

    @mcp.tool(annotations=READ_ONLY)
    def list_ad_keywords(campaign_id: str | None = None, ad_group_id: str | None = None, state: str | None = None,
                         country: str | None = None, next_token: str | None = None) -> dict:
        """Słowa kluczowe SP z keywordId, dopasowaniem i stawką (do zmian stawek w update_ad_bids)."""
        if not adv._live():
            return _mock_list("keywords")
        res = _list("keywords", adv._profile(country), campaign_id=campaign_id, ad_group_id=ad_group_id,
                    state=state, next_token=next_token)
        return {"mode": "live", "payload": {"keywords": res["items"]}, "next_token": res["next_token"]}

    @mcp.tool(annotations=READ_ONLY)
    def list_ad_targets(campaign_id: str | None = None, ad_group_id: str | None = None, state: str | None = None,
                        country: str | None = None, next_token: str | None = None) -> dict:
        """Targety SP (ASIN, kategorie, grupy auto: close/loose match, substitutes, complements) z targetId i stawką."""
        if not adv._live():
            return _mock_list("targets")
        res = _list("targets", adv._profile(country), campaign_id=campaign_id, ad_group_id=ad_group_id,
                    state=state, next_token=next_token)
        return {"mode": "live", "payload": {"targets": res["items"]}, "next_token": res["next_token"]}

    @mcp.tool(annotations=READ_ONLY)
    def list_ad_negatives(campaign_id: str | None = None, level: str = "ad_group", kind: str = "keywords",
                          ad_group_id: str | None = None, country: str | None = None,
                          next_token: str | None = None) -> dict:
        """Negatywy SP. level: ad_group albo campaign; kind: keywords (frazy) albo products (ASIN-y)."""
        resource = _negative_resource(level, kind)
        if not adv._live():
            return _mock_list(resource)
        res = _list(resource, adv._profile(country), campaign_id=campaign_id,
                    ad_group_id=ad_group_id if level == "ad_group" else None, next_token=next_token)
        return {"mode": "live", "payload": {"negatives": res["items"], "resource": resource},
                "next_token": res["next_token"]}

    @mcp.tool(annotations=READ_ONLY)
    def list_ad_changes(limit: int = 50, contains: str | None = None) -> dict:
        """Dziennik zmian w reklamach wykonanych przez ten serwer (najnowsze pierwsze). contains: filtr tekstowy."""
        return {"log": str(ads_log.log_path()), "changes": ads_log.read_changes(limit, contains)}

    # ------------------------------------------------------------------ zapis
    @mcp.tool(annotations=WRITE)
    def update_ad_bids(changes: list[dict], country: str | None = None, confirm: bool = False,
                       allow_big_change: bool = False) -> dict:
        """Zmień stawki lub stan (ENABLED/PAUSED) słów i targetów. Bez confirm=true podgląd przed → po.

        changes: lista {"keyword_id": "...", "bid": 0.45} albo {"target_id": "...", "state": "PAUSED"};
        w jednym elemencie bid i/lub state. Maks. 100 elementów naraz. Stawki w walucie profilu (podgląd ją
        pokazuje). Bezpiecznik: stawka > ok. 5 EUR albo > 3× obecnej wymaga allow_big_change=true.
        """
        if not changes or len(changes) > 100:
            raise AmazonAPIError("changes: od 1 do 100 elementów")
        groups: dict[str, list[dict]] = {"keywords": [], "targets": []}
        for ch in changes:
            resource = "keywords" if ch.get("keyword_id") else "targets" if ch.get("target_id") else None
            if not resource:
                raise AmazonAPIError(f"Element bez keyword_id/target_id: {ch}")
            item: dict[str, Any] = {ID_FIELD[resource]: str(ch.get("keyword_id") or ch.get("target_id"))}
            if ch.get("bid") is not None:
                item["bid"] = round(float(ch["bid"]), 2)
            if ch.get("state"):
                state = str(ch["state"]).upper()
                if state not in ("ENABLED", "PAUSED"):
                    raise AmazonAPIError("state: ENABLED albo PAUSED (archiwizacja tylko w konsoli)")
                item["state"] = state
            if len(item) == 1:
                raise AmazonAPIError(f"Element bez bid i state: {ch}")
            groups[resource].append(item)

        profile_id = _pid(country)
        currency = adv.profile_currency(profile_id)
        preview: list[dict] = []
        not_found: list[str] = []
        for resource, items in groups.items():
            if not items:
                continue
            current = {}
            if adv._live():
                ids = [i[ID_FIELD[resource]] for i in items]
                current = {str(x[ID_FIELD[resource]]): x for x in
                           _list(resource, profile_id, ids=ids, fetch_all=True)["items"]}
            for item in items:
                cur = current.get(item[ID_FIELD[resource]], {})
                if adv._live() and not cur:
                    not_found.append(item[ID_FIELD[resource]])
                    continue
                if "bid" in item:
                    item["bid"] = _check_bid(item["bid"], currency, cur.get("bid"), allow_big_change)
                row = {"type": resource[:-1], "id": item[ID_FIELD[resource]], "currency": currency or None,
                       "text": cur.get("keywordText") or cur.get("expression"),
                       "match_type": cur.get("matchType"), "campaign_id": cur.get("campaignId"),
                       "bid_before": cur.get("bid"), "bid_after": item.get("bid", cur.get("bid")),
                       "state_before": cur.get("state"), "state_after": item.get("state", cur.get("state"))}
                if cur.get("bid") and item.get("bid") and item["bid"] > BID_JUMP_WARN * float(cur["bid"]):
                    row["warning"] = f"stawka rośnie ponad {BID_JUMP_WARN:g}×"
                preview.append(row)
        if not_found:
            raise AmazonAPIError(f"ID nie istnieją w tym profilu (zły kraj albo ID): {not_found}. Nic nie wysłano.")

        def execute():
            if not adv._live():
                return {"mode": "mock", "payload": {"changed": preview}}
            calls = [("PUT", r, f"/sp/{r}", {KEY[r]: items}) for r, items in groups.items() if items]
            return _run_writes("update_ad_bids", profile_id, preview, calls)

        return guarded_write(confirm, f"Zmiana stawek/stanu: {len(preview)} pozycji", {"changes": preview}, execute)

    @mcp.tool(annotations=WRITE)
    def add_ad_negatives(campaign_id: str, keywords: list[str] | None = None, asins: list[str] | None = None,
                         ad_group_id: str | None = None, match_type: str = "NEGATIVE_EXACT",
                         country: str | None = None, confirm: bool = False) -> dict:
        """Dodaj negatywy: frazy (keywords) i/lub ASIN-y (asins). Z ad_group_id na poziomie grupy, bez niego na
        poziomie kampanii. match_type: NEGATIVE_EXACT albo NEGATIVE_PHRASE. Duplikaty istniejących są pomijane.
        ASIN-y na poziomie kampanii Amazon przyjmuje sprzedawcy tylko w kampaniach auto; w manualnych podaj ad_group_id.
        """
        match_type = match_type.upper()
        if match_type not in NEGATIVE_MATCH_TYPES:
            raise AmazonAPIError(f"match_type: {', '.join(NEGATIVE_MATCH_TYPES)}")
        keywords = [k.strip() for k in (keywords or []) if k.strip()]
        asins = [a.strip().upper() for a in (asins or []) if a.strip()]
        if not keywords and not asins:
            raise AmazonAPIError("Podaj keywords i/lub asins")
        level = "ad_group" if ad_group_id else "campaign"
        kw_res, pt_res = _negative_resource(level, "keywords"), _negative_resource(level, "products")
        profile_id = _pid(country)

        existing_kw, existing_asin = set(), set()
        if adv._live():
            for x in _list(kw_res, profile_id, campaign_id=campaign_id, ad_group_id=ad_group_id, fetch_all=True)["items"]:
                if x.get("state") != "ARCHIVED":
                    existing_kw.add((x.get("keywordText", "").lower(), x.get("matchType")))
            for x in _list(pt_res, profile_id, campaign_id=campaign_id, ad_group_id=ad_group_id, fetch_all=True)["items"]:
                if x.get("state") != "ARCHIVED":
                    for e in x.get("expression") or []:
                        existing_asin.add(str(e.get("value", "")).upper())
        base = {"campaignId": str(campaign_id), "state": "ENABLED"}
        if ad_group_id:
            base["adGroupId"] = str(ad_group_id)
        new_kw = [{**base, "keywordText": k, "matchType": match_type} for k in dict.fromkeys(keywords)
                  if (k.lower(), match_type) not in existing_kw]
        new_pt = [{**base, "expression": [{"type": "ASIN_SAME_AS", "value": a}]} for a in dict.fromkeys(asins)
                  if a not in existing_asin]
        skipped = [k for k in keywords if (k.lower(), match_type) in existing_kw] + \
                  [a for a in asins if a in existing_asin]
        request = {"level": level, "campaign_id": campaign_id, "ad_group_id": ad_group_id,
                   "keywords": [k["keywordText"] for k in new_kw], "match_type": match_type,
                   "asins": [p["expression"][0]["value"] for p in new_pt], "skipped_duplicates": skipped}
        if not new_kw and not new_pt:
            return {"status": "nothing_to_do", "request": request}

        def execute():
            if not adv._live():
                return {"mode": "mock", "payload": request}
            calls = [("POST", r, f"/sp/{r}", {KEY[r]: items}) for r, items in ((kw_res, new_kw), (pt_res, new_pt))
                     if items]
            return _run_writes("add_ad_negatives", profile_id, [request], calls)

        return guarded_write(confirm, f"Negatywy ({level}) w kampanii {campaign_id}", request, execute)

    @mcp.tool(annotations=WRITE)
    def remove_ad_negatives(negative_ids: list[str], level: str = "ad_group", kind: str = "keywords",
                            country: str | None = None, confirm: bool = False) -> dict:
        """Usuń (zarchiwizuj) negatywy po ID z list_ad_negatives: cofnięcie negacji. level/kind jak w list_ad_negatives."""
        resource = _negative_resource(level, kind)
        if not negative_ids:
            raise AmazonAPIError("Podaj negative_ids")
        profile_id = _pid(country)
        found = []
        if adv._live():
            found = _list(resource, profile_id, ids=[str(i) for i in negative_ids], fetch_all=True)["items"]
        request = {"resource": resource, "ids": [str(i) for i in negative_ids],
                   "found": [{"id": x.get(ID_FIELD[resource]), "text": x.get("keywordText") or x.get("expression"),
                              "match_type": x.get("matchType"), "campaign_id": x.get("campaignId")} for x in found]}
        missing = sorted(set(request["ids"]) - {str(x.get(ID_FIELD[resource])) for x in found})
        if adv._live() and missing:
            raise AmazonAPIError(f"Negatywy {missing} nie istnieją w {resource} tego profilu (zły kraj, poziom lub rodzaj)")

        def execute():
            if not adv._live():
                return {"mode": "mock", "payload": request}
            calls = [("POST", resource, f"/sp/{resource}/delete", {ID_FILTER[resource]: {"include": request["ids"]}})]
            return _run_writes("remove_ad_negatives", profile_id, [request], calls)

        return guarded_write(confirm, f"Usunięcie {len(request['ids'])} negatywów ({resource})", request, execute)

    @mcp.tool(annotations=WRITE)
    def add_ad_keywords(campaign_id: str, ad_group_id: str, keywords: list[dict] | None = None,
                        asins: list[dict] | None = None, country: str | None = None, confirm: bool = False,
                        allow_big_change: bool = False) -> dict:
        """Dodaj słowa i targety ASIN do istniejącej grupy reklam (harvest / import do exact).

        keywords: [{"text": "hundebett xxl", "match_type": "EXACT", "bid": 0.80}];
        asins: [{"asin": "B0...", "bid": 0.50}]. Duplikaty istniejących w grupie są pomijane. Stawki w walucie
        profilu; bezpiecznik ok. 5 EUR (powyżej tylko z allow_big_change=true).
        """
        keywords, asins = keywords or [], asins or []
        if not keywords and not asins:
            raise AmazonAPIError("Podaj keywords i/lub asins")
        profile_id = _pid(country)
        currency = adv.profile_currency(profile_id)
        existing_kw, existing_asin = set(), set()
        if adv._live():
            for x in _list("keywords", profile_id, ad_group_id=ad_group_id, fetch_all=True)["items"]:
                if x.get("state") != "ARCHIVED":
                    existing_kw.add((x.get("keywordText", "").lower(), x.get("matchType")))
            for x in _list("targets", profile_id, ad_group_id=ad_group_id, fetch_all=True)["items"]:
                if x.get("state") != "ARCHIVED":
                    for e in x.get("expression") or []:
                        existing_asin.add(str(e.get("value", "")).upper())
        base = {"campaignId": str(campaign_id), "adGroupId": str(ad_group_id), "state": "ENABLED"}
        new_kw, new_pt, skipped = [], [], []
        for k in keywords:
            text, mt = str(k.get("text", "")).strip(), str(k.get("match_type", "EXACT")).upper()
            if not text or mt not in MATCH_TYPES:
                raise AmazonAPIError(f"Słowo wymaga text i match_type z {MATCH_TYPES}: {k}")
            if (text.lower(), mt) in existing_kw:
                skipped.append(f"{text} [{mt}]")
                continue
            item = {**base, "keywordText": text, "matchType": mt}
            if k.get("bid") is not None:
                item["bid"] = _check_bid(k["bid"], currency, allow_big_change=allow_big_change)
            new_kw.append(item)
            existing_kw.add((text.lower(), mt))
        for a in asins:
            asin = str(a.get("asin", "")).strip().upper()
            if not asin:
                raise AmazonAPIError(f"Target wymaga asin: {a}")
            if asin in existing_asin:
                skipped.append(asin)
                continue
            item = {**base, "expression": [{"type": "ASIN_SAME_AS", "value": asin}], "expressionType": "MANUAL"}
            if a.get("bid") is not None:
                item["bid"] = _check_bid(a["bid"], currency, allow_big_change=allow_big_change)
            new_pt.append(item)
            existing_asin.add(asin)
        request = {"campaign_id": campaign_id, "ad_group_id": ad_group_id, "currency": currency or None,
                   "keywords": [{"text": k["keywordText"], "match_type": k["matchType"], "bid": k.get("bid")}
                                for k in new_kw],
                   "asins": [{"asin": p["expression"][0]["value"], "bid": p.get("bid")} for p in new_pt],
                   "skipped_duplicates": skipped}
        if not new_kw and not new_pt:
            return {"status": "nothing_to_do", "request": request}

        def execute():
            if not adv._live():
                return {"mode": "mock", "payload": request}
            calls = [("POST", r, f"/sp/{r}", {KEY[r]: items}) for r, items in (("keywords", new_kw), ("targets", new_pt))
                     if items]
            return _run_writes("add_ad_keywords", profile_id, [request], calls)

        return guarded_write(confirm, f"Nowe słowa/targety w grupie {ad_group_id}", request, execute)

    @mcp.tool(annotations=WRITE)
    def update_ad_placements(campaign_id: str, top_of_search: int | None = None, product_page: int | None = None,
                             rest_of_search: int | None = None, country: str | None = None,
                             confirm: bool = False) -> dict:
        """Zmień modyfikatory placementów kampanii w % (0–900): góra wyszukiwania, strona produktu, reszta
        wyszukiwania. Niepodane zostają bez zmian. Bez confirm=true podgląd przed → po.
        """
        new = {PLACEMENTS[k]: v for k, v in
               (("top_of_search", top_of_search), ("product_page", product_page), ("rest_of_search", rest_of_search))
               if v is not None}
        if not new:
            raise AmazonAPIError("Podaj co najmniej jeden placement")
        for v in new.values():
            if not 0 <= int(v) <= 900:
                raise AmazonAPIError("Modyfikator placementu: 0–900 %")
        profile_id = _pid(country)
        before: dict[str, int] = {}
        strategy = None
        name = None
        cohorts = None
        if adv._live():
            body = {"campaignIdFilter": {"include": [str(campaign_id)]}, "maxResults": 10}
            found = (adv.ads.request("POST", "/sp/campaigns/list", json=body, media_type=MT["campaigns"],
                                     profile_id=profile_id) or {}).get("campaigns", [])
            if not found:
                raise AmazonAPIError(f"Kampania {campaign_id} nie istnieje w tym profilu (sprawdź country)")
            dyn = found[0].get("dynamicBidding") or {}
            strategy, name = dyn.get("strategy"), found[0].get("name")
            cohorts = dyn.get("shopperCohortBidding")  # przepisujemy bez zmian, żeby PUT ich nie skasował
            before = {p["placement"]: p["percentage"] for p in dyn.get("placementBidding") or []}
        after = {**before, **{k: int(v) for k, v in new.items()}}
        request = {"campaign_id": campaign_id, "campaign_name": name, "strategy": strategy,
                   "before": before, "after": after}

        def execute():
            if not adv._live():
                return {"mode": "mock", "payload": request}
            dynamic: dict[str, Any] = {"placementBidding": [{"placement": p, "percentage": v} for p, v in after.items()]}
            if strategy:
                dynamic["strategy"] = strategy
            if cohorts:
                dynamic["shopperCohortBidding"] = cohorts
            body = {"campaigns": [{"campaignId": str(campaign_id), "dynamicBidding": dynamic}]}
            return _run_writes("update_ad_placements", profile_id, [request], [("PUT", "campaigns", "/sp/campaigns", body)])

        return guarded_write(confirm, f"Placementy kampanii {campaign_id}", request, execute)

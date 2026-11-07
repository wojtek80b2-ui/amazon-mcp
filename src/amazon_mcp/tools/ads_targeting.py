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
PLACEMENTS = {"top_of_search": "PLACEMENT_TOP", "product_page": "PLACEMENT_PRODUCT_PAGE",
              "rest_of_search": "PLACEMENT_REST_OF_SEARCH"}
MATCH_TYPES = ("EXACT", "PHRASE", "BROAD")
NEGATIVE_MATCH_TYPES = ("NEGATIVE_EXACT", "NEGATIVE_PHRASE")
MIN_BID = 0.02  # minimalna stawka SP na rynkach EUR
BID_JUMP_WARN = 2.0  # podgląd ostrzega, gdy nowa stawka > 2× obecnej


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
        id_filter = "keywordIdFilter" if ID_FIELD[resource] == "keywordId" else "targetIdFilter"
        body[id_filter] = {"include": [str(i) for i in ids]}
    if state:
        body["stateFilter"] = {"include": [state.upper()]}
    if next_token:
        body["nextToken"] = next_token
    items: list = []
    while True:
        data = adv.ads.request("POST", f"/sp/{resource}/list", json=body, media_type=MT[resource],
                               profile_id=profile_id) or {}
        items.extend(data.get(KEY[resource], []))
        token = data.get("nextToken")
        if not (fetch_all and token):
            return {"items": items, "next_token": token}
        body["nextToken"] = token


def _errors(data: dict | None, resource: str) -> list:
    return ((data or {}).get(KEY[resource]) or {}).get("error") or []


def _successes(data: dict | None, resource: str) -> list:
    return ((data or {}).get(KEY[resource]) or {}).get("success") or []


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
    def update_ad_bids(changes: list[dict], country: str | None = None, confirm: bool = False) -> dict:
        """Zmień stawki lub stan (ENABLED/PAUSED) słów i targetów. Bez confirm=true podgląd przed → po.

        changes: lista {"keyword_id": "...", "bid": 0.45} albo {"target_id": "...", "state": "PAUSED"};
        w jednym elemencie bid i/lub state. Maks. 100 elementów naraz.
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
                bid = round(float(ch["bid"]), 2)
                if bid < MIN_BID:
                    raise AmazonAPIError(f"Stawka {bid} poniżej minimum {MIN_BID}")
                item["bid"] = bid
            if ch.get("state"):
                state = str(ch["state"]).upper()
                if state not in ("ENABLED", "PAUSED"):
                    raise AmazonAPIError("state: ENABLED albo PAUSED (archiwizacja tylko w konsoli)")
                item["state"] = state
            if len(item) == 1:
                raise AmazonAPIError(f"Element bez bid i state: {ch}")
            groups[resource].append(item)

        profile_id = adv._profile(country) if adv._live() else None
        preview: list[dict] = []
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
                row = {"type": resource[:-1], "id": item[ID_FIELD[resource]],
                       "text": cur.get("keywordText") or cur.get("expression"),
                       "match_type": cur.get("matchType"), "campaign_id": cur.get("campaignId"),
                       "bid_before": cur.get("bid"), "bid_after": item.get("bid", cur.get("bid")),
                       "state_before": cur.get("state"), "state_after": item.get("state", cur.get("state"))}
                if adv._live() and not cur:
                    row["warning"] = "NIE ZNALEZIONO w tym profilu (zły kraj albo ID)"
                elif cur.get("bid") and item.get("bid") and item["bid"] > BID_JUMP_WARN * float(cur["bid"]):
                    row["warning"] = f"stawka rośnie ponad {BID_JUMP_WARN:g}×"
                preview.append(row)

        def execute():
            if not adv._live():
                return {"mode": "mock", "payload": {"changed": preview}}
            results, errors = {}, []
            for resource, items in groups.items():
                if items:
                    data = adv.ads.request("PUT", f"/sp/{resource}", json={KEY[resource]: items},
                                           media_type=MT[resource], profile_id=profile_id)
                    results[resource] = len(_successes(data, resource))
                    errors += _errors(data, resource)
            outcome = {"success": results, "errors": errors}
            log = ads_log.log_change("update_ad_bids", profile_id, preview, outcome)
            return {"mode": "live", "payload": outcome, "change_log": log}

        return guarded_write(confirm, f"Zmiana stawek/stanu: {len(preview)} pozycji", {"changes": preview}, execute)

    @mcp.tool(annotations=WRITE)
    def add_ad_negatives(campaign_id: str, keywords: list[str] | None = None, asins: list[str] | None = None,
                         ad_group_id: str | None = None, match_type: str = "NEGATIVE_EXACT",
                         country: str | None = None, confirm: bool = False) -> dict:
        """Dodaj negatywy: frazy (keywords) i/lub ASIN-y (asins). Z ad_group_id na poziomie grupy, bez niego na
        poziomie kampanii. match_type: NEGATIVE_EXACT albo NEGATIVE_PHRASE. Duplikaty istniejących są pomijane.
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
        profile_id = adv._profile(country) if adv._live() else None

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
            outcome: dict[str, Any] = {"created": [], "errors": []}
            for resource, items in ((kw_res, new_kw), (pt_res, new_pt)):
                if items:
                    data = adv.ads.request("POST", f"/sp/{resource}", json={KEY[resource]: items},
                                           media_type=MT[resource], profile_id=profile_id)
                    outcome["created"] += [{"resource": resource, **s} for s in _successes(data, resource)]
                    outcome["errors"] += _errors(data, resource)
            log = ads_log.log_change("add_ad_negatives", profile_id, [request], outcome)
            return {"mode": "live", "payload": outcome, "change_log": log}

        return guarded_write(confirm, f"Negatywy ({level}) w kampanii {campaign_id}", request, execute)

    @mcp.tool(annotations=WRITE)
    def remove_ad_negatives(negative_ids: list[str], level: str = "ad_group", kind: str = "keywords",
                            country: str | None = None, confirm: bool = False) -> dict:
        """Usuń (zarchiwizuj) negatywy po ID z list_ad_negatives: cofnięcie negacji. level/kind jak w list_ad_negatives."""
        resource = _negative_resource(level, kind)
        if not negative_ids:
            raise AmazonAPIError("Podaj negative_ids")
        profile_id = adv._profile(country) if adv._live() else None
        found = []
        if adv._live():
            found = _list(resource, profile_id, ids=[str(i) for i in negative_ids], fetch_all=True)["items"]
        request = {"resource": resource, "ids": [str(i) for i in negative_ids],
                   "found": [{"id": x.get(ID_FIELD[resource]), "text": x.get("keywordText") or x.get("expression"),
                              "match_type": x.get("matchType"), "campaign_id": x.get("campaignId")} for x in found]}
        id_filter = "keywordIdFilter" if ID_FIELD[resource] == "keywordId" else "targetIdFilter"

        def execute():
            if not adv._live():
                return {"mode": "mock", "payload": request}
            data = adv.ads.request("POST", f"/sp/{resource}/delete",
                                   json={id_filter: {"include": request["ids"]}},
                                   media_type=MT[resource], profile_id=profile_id)
            outcome = {"success": len(_successes(data, resource)), "errors": _errors(data, resource)}
            log = ads_log.log_change("remove_ad_negatives", profile_id, [request], outcome)
            return {"mode": "live", "payload": outcome, "change_log": log}

        return guarded_write(confirm, f"Usunięcie {len(request['ids'])} negatywów ({resource})", request, execute)

    @mcp.tool(annotations=WRITE)
    def add_ad_keywords(campaign_id: str, ad_group_id: str, keywords: list[dict] | None = None,
                        asins: list[dict] | None = None, country: str | None = None, confirm: bool = False) -> dict:
        """Dodaj słowa i targety ASIN do istniejącej grupy reklam (harvest / import do exact).

        keywords: [{"text": "hundebett xxl", "match_type": "EXACT", "bid": 0.80}];
        asins: [{"asin": "B0...", "bid": 0.50}]. Duplikaty istniejących w grupie są pomijane.
        """
        keywords, asins = keywords or [], asins or []
        if not keywords and not asins:
            raise AmazonAPIError("Podaj keywords i/lub asins")
        profile_id = adv._profile(country) if adv._live() else None
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
                item["bid"] = max(MIN_BID, round(float(k["bid"]), 2))
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
                item["bid"] = max(MIN_BID, round(float(a["bid"]), 2))
            new_pt.append(item)
            existing_asin.add(asin)
        request = {"campaign_id": campaign_id, "ad_group_id": ad_group_id,
                   "keywords": [{"text": k["keywordText"], "match_type": k["matchType"], "bid": k.get("bid")}
                                for k in new_kw],
                   "asins": [{"asin": p["expression"][0]["value"], "bid": p.get("bid")} for p in new_pt],
                   "skipped_duplicates": skipped}
        if not new_kw and not new_pt:
            return {"status": "nothing_to_do", "request": request}

        def execute():
            if not adv._live():
                return {"mode": "mock", "payload": request}
            outcome: dict[str, Any] = {"created": [], "errors": []}
            for resource, items in (("keywords", new_kw), ("targets", new_pt)):
                if items:
                    data = adv.ads.request("POST", f"/sp/{resource}", json={KEY[resource]: items},
                                           media_type=MT[resource], profile_id=profile_id)
                    outcome["created"] += [{"resource": resource, **s} for s in _successes(data, resource)]
                    outcome["errors"] += _errors(data, resource)
            log = ads_log.log_change("add_ad_keywords", profile_id, [request], outcome)
            return {"mode": "live", "payload": outcome, "change_log": log}

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
        profile_id = adv._profile(country) if adv._live() else None
        before: dict[str, int] = {}
        strategy = None
        name = None
        if adv._live():
            body = {"campaignIdFilter": {"include": [str(campaign_id)]}, "maxResults": 10}
            found = (adv.ads.request("POST", "/sp/campaigns/list", json=body, media_type=MT["campaigns"],
                                     profile_id=profile_id) or {}).get("campaigns", [])
            if not found:
                raise AmazonAPIError(f"Kampania {campaign_id} nie istnieje w tym profilu (sprawdź country)")
            dyn = found[0].get("dynamicBidding") or {}
            strategy, name = dyn.get("strategy"), found[0].get("name")
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
            data = adv.ads.request("PUT", "/sp/campaigns",
                                   json={"campaigns": [{"campaignId": str(campaign_id), "dynamicBidding": dynamic}]},
                                   media_type=MT["campaigns"], profile_id=profile_id)
            outcome = {"success": len(_successes(data, "campaigns")), "errors": _errors(data, "campaigns")}
            log = ads_log.log_change("update_ad_placements", profile_id, [request], outcome)
            if outcome["errors"]:
                raise AmazonAPIError(f"Ads API odrzuciło zmianę placementów: {outcome['errors']} (dziennik: {log})")
            return {"mode": "live", "payload": outcome, "change_log": log}

        return guarded_write(confirm, f"Placementy kampanii {campaign_id}", request, execute)

"""Dane testowe w formacie odpowiedzi SP-API (tryb AMAZON_MODE=mock).

Struktury odwzorowują pola z dokumentacji SP-API, więc kod narzędzi i prompty
działają tak samo po przełączeniu na prawdziwe dane.
"""

from __future__ import annotations

MARKETPLACE_PL = "A1C3SOZRARQ6R3"

PRODUCTS = [
    {"sku": "KUBEK-001", "asin": "B0MOCK0001", "title": "Kubek ceramiczny 350 ml, biały", "price": 39.99, "fnsku": "X00MOCK001"},
    {"sku": "BUTELKA-002", "asin": "B0MOCK0002", "title": "Butelka termiczna 750 ml, stal", "price": 89.00, "fnsku": "X00MOCK002"},
    {"sku": "TORBA-003", "asin": "B0MOCK0003", "title": "Torba bawełniana na zakupy", "price": 24.50, "fnsku": "X00MOCK003"},
]


def _money(amount: float, currency: str = "PLN") -> dict:
    return {"CurrencyCode": currency, "Amount": f"{amount:.2f}"}


ORDERS = [
    {
        "AmazonOrderId": "405-0000001-0000001",
        "PurchaseDate": "2026-09-25T10:12:00Z",
        "LastUpdateDate": "2026-09-25T14:00:00Z",
        "OrderStatus": "Shipped",
        "FulfillmentChannel": "AFN",
        "SalesChannel": "Amazon.pl",
        "OrderTotal": _money(79.98),
        "NumberOfItemsShipped": 2,
        "NumberOfItemsUnshipped": 0,
        "MarketplaceId": MARKETPLACE_PL,
        "ShipServiceLevel": "Standard",
        "IsPrime": True,
    },
    {
        "AmazonOrderId": "405-0000002-0000002",
        "PurchaseDate": "2026-09-26T08:45:00Z",
        "LastUpdateDate": "2026-09-26T08:50:00Z",
        "OrderStatus": "Unshipped",
        "FulfillmentChannel": "MFN",
        "SalesChannel": "Amazon.pl",
        "OrderTotal": _money(89.00),
        "NumberOfItemsShipped": 0,
        "NumberOfItemsUnshipped": 1,
        "MarketplaceId": MARKETPLACE_PL,
        "ShipServiceLevel": "Standard",
        "IsPrime": False,
    },
    {
        "AmazonOrderId": "405-0000003-0000003",
        "PurchaseDate": "2026-09-27T07:30:00Z",
        "LastUpdateDate": "2026-09-27T07:31:00Z",
        "OrderStatus": "Pending",
        "FulfillmentChannel": "AFN",
        "SalesChannel": "Amazon.pl",
        "OrderTotal": _money(24.50),
        "NumberOfItemsShipped": 0,
        "NumberOfItemsUnshipped": 1,
        "MarketplaceId": MARKETPLACE_PL,
        "ShipServiceLevel": "Expedited",
        "IsPrime": True,
    },
]

ORDER_ITEMS = {
    "405-0000001-0000001": [
        {"ASIN": "B0MOCK0001", "SellerSKU": "KUBEK-001", "OrderItemId": "10001", "Title": PRODUCTS[0]["title"],
         "QuantityOrdered": 2, "QuantityShipped": 2, "ItemPrice": _money(79.98)},
    ],
    "405-0000002-0000002": [
        {"ASIN": "B0MOCK0002", "SellerSKU": "BUTELKA-002", "OrderItemId": "10002", "Title": PRODUCTS[1]["title"],
         "QuantityOrdered": 1, "QuantityShipped": 0, "ItemPrice": _money(89.00)},
    ],
    "405-0000003-0000003": [
        {"ASIN": "B0MOCK0003", "SellerSKU": "TORBA-003", "OrderItemId": "10003", "Title": PRODUCTS[2]["title"],
         "QuantityOrdered": 1, "QuantityShipped": 0, "ItemPrice": _money(24.50)},
    ],
}

FBA_INVENTORY = {
    "granularity": {"granularityType": "Marketplace", "granularityId": MARKETPLACE_PL},
    "inventorySummaries": [
        {"asin": p["asin"], "fnSku": p["fnsku"], "sellerSku": p["sku"], "condition": "NewItem",
         "productName": p["title"], "totalQuantity": qty,
         "inventoryDetails": {"fulfillableQuantity": qty - res, "reservedQuantity": {"totalReservedQuantity": res},
                              "inboundWorkingQuantity": inbound}}
        for p, qty, res, inbound in zip(PRODUCTS, (120, 8, 0), (5, 2, 0), (0, 50, 0))
    ],
}

COMPETITIVE_PRICING = [
    {"ASIN": p["asin"], "status": "Success",
     "Product": {"CompetitivePricing": {
         "CompetitivePrices": [{"CompetitivePriceId": "1", "condition": "New", "belongsToRequester": i != 1,
                                "Price": {"LandedPrice": _money(p["price"] - (3 if i == 1 else 0)),
                                          "ListingPrice": _money(p["price"] - (3 if i == 1 else 0))}}],
         "NumberOfOfferListings": [{"condition": "New", "Count": 1 + i}]}}}
    for i, p in enumerate(PRODUCTS)
]


def item_offers(asin: str) -> dict:
    p = next((x for x in PRODUCTS if x["asin"] == asin), PRODUCTS[0])
    return {
        "ASIN": asin, "status": "Success", "ItemCondition": "New",
        "Summary": {"TotalOfferCount": 2, "LowestPrices": [{"condition": "new", "fulfillmentChannel": "Amazon",
                                                            "LandedPrice": _money(p["price"] - 1)}],
                    "BuyBoxPrices": [{"condition": "New", "LandedPrice": _money(p["price"])}]},
        "Offers": [
            {"SellerId": "A1MOCKSELLER", "IsBuyBoxWinner": True, "IsFulfilledByAmazon": True,
             "ListingPrice": _money(p["price"]), "Shipping": _money(0)},
            {"SellerId": "A2COMPETITOR", "IsBuyBoxWinner": False, "IsFulfilledByAmazon": True,
             "ListingPrice": _money(p["price"] - 1), "Shipping": _money(0)},
        ],
    }


def listing(sku: str) -> dict:
    p = next((x for x in PRODUCTS if x["sku"] == sku), None)
    if p is None:
        return {"sku": sku, "errors": [{"code": "NOT_FOUND", "message": f"Brak SKU {sku} (mock)"}]}
    return {
        "sku": p["sku"],
        "summaries": [{"marketplaceId": MARKETPLACE_PL, "asin": p["asin"], "productType": "DRINKING_CUP",
                       "conditionType": "new_new", "status": ["BUYABLE", "DISCOVERABLE"], "itemName": p["title"]}],
        "attributes": {"purchasable_offer": [{"currency": "PLN", "our_price": [{"schedule": [{"value_with_tax": p["price"]}]}]}]},
        "issues": [],
    }


LISTINGS_SEARCH = {"numberOfResults": len(PRODUCTS), "items": [listing(p["sku"]) for p in PRODUCTS]}

CATALOG_ITEM = {
    "asin": "B0MOCK0001",
    "summaries": [{"marketplaceId": MARKETPLACE_PL, "brand": "MockBrand", "itemName": PRODUCTS[0]["title"],
                   "manufacturer": "MockBrand Sp. z o.o."}],
    "salesRanks": [{"marketplaceId": MARKETPLACE_PL, "displayGroupRanks": [{"title": "Kuchnia i dom", "rank": 1520}]}],
}

REPORTS = {
    "reports": [
        {"reportId": "50001", "reportType": "GET_MERCHANT_LISTINGS_ALL_DATA", "processingStatus": "DONE",
         "createdTime": "2026-09-26T06:00:00Z", "reportDocumentId": "amzn1.tortuga.mock.doc1",
         "marketplaceIds": [MARKETPLACE_PL]},
        {"reportId": "50002", "reportType": "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL",
         "processingStatus": "IN_PROGRESS", "createdTime": "2026-09-27T06:00:00Z", "marketplaceIds": [MARKETPLACE_PL]},
    ]
}

REPORT_DOCUMENT = {
    "reportDocumentId": "amzn1.tortuga.mock.doc1",
    "document": "seller-sku\tasin1\titem-name\tprice\tquantity\n"
    + "".join(f"{p['sku']}\t{p['asin']}\t{p['title']}\t{p['price']:.2f}\t10\n" for p in PRODUCTS),
}

FINANCIAL_EVENTS = {
    "FinancialEvents": {
        "ShipmentEventList": [
            {"AmazonOrderId": "405-0000001-0000001", "PostedDate": "2026-09-25T14:00:00Z",
             "ShipmentItemList": [{"SellerSKU": "KUBEK-001", "QuantityShipped": 2,
                                   "ItemChargeList": [{"ChargeType": "Principal", "ChargeAmount": _money(79.98)}],
                                   "ItemFeeList": [{"FeeType": "Commission", "FeeAmount": _money(-12.00)},
                                                   {"FeeType": "FBAPerUnitFulfillmentFee", "FeeAmount": _money(-15.40)}]}]}
        ],
        "RefundEventList": [],
        "ServiceFeeEventList": [],
    }
}

FEE_ESTIMATE = {
    "FeesEstimateResult": {
        "Status": "Success",
        "FeesEstimate": {
            "TotalFeesEstimate": _money(13.70),
            "FeeDetailList": [
                {"FeeType": "ReferralFee", "FinalFee": _money(6.00)},
                {"FeeType": "FBAFees", "FinalFee": _money(7.70)},
            ],
        },
    }
}

MARKETPLACE_PARTICIPATION = [
    {"marketplace": {"id": MARKETPLACE_PL, "name": "Amazon.pl", "countryCode": "PL", "defaultCurrencyCode": "PLN"},
     "participation": {"isParticipating": True, "hasSuspendedListings": False}},
    {"marketplace": {"id": "A1PA6795UKMFR9", "name": "Amazon.de", "countryCode": "DE", "defaultCurrencyCode": "EUR"},
     "participation": {"isParticipating": True, "hasSuspendedListings": False}},
]

FEEDS = {"feeds": [{"feedId": "70001", "feedType": "JSON_LISTINGS_FEED", "processingStatus": "DONE",
                    "createdTime": "2026-09-20T09:00:00Z", "resultFeedDocumentId": "amzn1.tortuga.mock.feed1"}]}

AD_CAMPAIGNS = [
    {"campaignId": "900001", "name": "SP - Kubki - Auto", "campaignType": "sponsoredProducts", "targetingType": "AUTO",
     "state": "ENABLED", "dailyBudget": 30.0, "startDate": "20260901",
     "metrics": {"impressions": 15230, "clicks": 212, "cost": 101.76, "sales": 639.84, "acos": 15.9}},
    {"campaignId": "900002", "name": "SP - Butelki - Manual", "campaignType": "sponsoredProducts", "targetingType": "MANUAL",
     "state": "PAUSED", "dailyBudget": 20.0, "startDate": "20260910",
     "metrics": {"impressions": 4100, "clicks": 51, "cost": 38.25, "sales": 89.00, "acos": 43.0}},
]

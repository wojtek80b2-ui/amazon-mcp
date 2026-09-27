"""Finances API v0."""

from datetime import datetime, timedelta, timezone

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def list_financial_events(
        posted_after: str | None = None,
        posted_before: str | None = None,
        max_results: int = 100,
        next_token: str | None = None,
    ) -> dict:
        """Zdarzenia finansowe: sprzedaż, prowizje, opłaty FBA, zwroty. Domyślnie ostatnie 7 dni."""
        if next_token:
            params = {"NextToken": next_token}
        else:
            after = posted_after or (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            params = {"PostedAfter": after, "MaxResultsPerPage": min(max_results, 100)}
            if posted_before:
                params["PostedBefore"] = posted_before
        return spapi.call("FinancesV0", "list_financial_events", mock=mock_data.FINANCIAL_EVENTS, **params)

    @mcp.tool(annotations=READ_ONLY)
    def get_order_financial_events(order_id: str) -> dict:
        """Rozliczenie jednego zamówienia: przychód, prowizja Amazon, opłaty FBA, zwroty."""
        return spapi.call("FinancesV0", "get_financial_events_for_order", order_id,
                          mock=mock_data.FINANCIAL_EVENTS)

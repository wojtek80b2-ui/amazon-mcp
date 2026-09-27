"""Feeds API 2021-06-30 (masowe operacje na ofertach)."""

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def list_feeds(feed_types: list[str] | None = None, page_size: int = 20) -> dict:
        """Lista wysłanych feedów (np. JSON_LISTINGS_FEED) i ich status przetwarzania."""
        params = {"pageSize": min(page_size, 100)}
        if feed_types:
            params["feedTypes"] = feed_types
        return spapi.call("FeedsV20210630", "get_feeds", mock=mock_data.FEEDS, **params)

    @mcp.tool(annotations=READ_ONLY)
    def get_feed(feed_id: str) -> dict:
        """Status jednego feedu. Gdy DONE, resultFeedDocumentId wskazuje raport z wynikami."""
        return spapi.call("FeedsV20210630", "get_feed", feed_id,
                          mock=lambda: next((f for f in mock_data.FEEDS["feeds"] if f["feedId"] == feed_id), None))

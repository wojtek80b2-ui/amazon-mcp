"""Product Fees API v0."""

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def estimate_fees(
        asin: str,
        price: float,
        currency: str = "PLN",
        is_fba: bool = True,
        marketplace: str | None = None,
    ) -> dict:
        """Szacunkowe opłaty Amazon (prowizja + FBA) dla ASIN-u przy danej cenie."""
        return spapi.call("ProductFees", "get_product_fees_estimate_for_asin", asin, price,
                          currency=currency, is_fba=is_fba, marketplace=marketplace,
                          mock=mock_data.FEE_ESTIMATE)

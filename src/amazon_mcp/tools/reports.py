"""Reports API 2021-06-30."""

from amazon_mcp import mock_data
from amazon_mcp.client import spapi
from amazon_mcp.tools._common import READ_ONLY, WRITE

MAX_DOCUMENT_CHARS = 50_000


def register(mcp) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def list_reports(
        report_types: list[str] | None = None,
        processing_statuses: list[str] | None = None,
        page_size: int = 20,
        next_token: str | None = None,
    ) -> dict:
        """Lista wygenerowanych raportów. processing_statuses: IN_QUEUE, IN_PROGRESS, DONE, CANCELLED, FATAL."""
        params = {"pageSize": min(page_size, 100)}
        if next_token:
            params = {"nextToken": next_token}
        else:
            if report_types:
                params["reportTypes"] = report_types
            if processing_statuses:
                params["processingStatuses"] = processing_statuses
        return spapi.call("Reports", "get_reports", mock=mock_data.REPORTS, **params)

    @mcp.tool(annotations=WRITE)
    def create_report(
        report_type: str,
        start_time: str | None = None,
        end_time: str | None = None,
        marketplace: str | None = None,
    ) -> dict:
        """Zleć wygenerowanie raportu. Zwraca reportId; status sprawdzisz narzędziem get_report.

        Popularne typy: GET_MERCHANT_LISTINGS_ALL_DATA, GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL,
        GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA, GET_SALES_AND_TRAFFIC_REPORT,
        GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE, GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA.
        """
        body = {"reportType": report_type, "marketplaceIds": [spapi.marketplace_id(marketplace)]}
        if start_time:
            body["dataStartTime"] = start_time
        if end_time:
            body["dataEndTime"] = end_time
        return spapi.call("Reports", "create_report", marketplace=marketplace,
                          mock={"reportId": "50003"}, **body)

    @mcp.tool(annotations=READ_ONLY)
    def get_report(report_id: str) -> dict:
        """Status raportu. Gdy processingStatus=DONE, pole reportDocumentId wskazuje dokument do pobrania."""
        return spapi.call("Reports", "get_report", report_id,
                          mock=lambda: next((r for r in mock_data.REPORTS["reports"] if r["reportId"] == report_id),
                                            {"reportId": report_id, "processingStatus": "IN_QUEUE"}))

    @mcp.tool(annotations=READ_ONLY)
    def get_report_document(report_document_id: str, max_chars: int = MAX_DOCUMENT_CHARS) -> dict:
        """Pobierz i rozpakuj treść gotowego raportu (zwykle TSV). Długie raporty są przycinane do max_chars."""
        result = spapi.call("Reports", "get_report_document", report_document_id, download=True,
                            mock=mock_data.REPORT_DOCUMENT)
        doc = result["payload"].get("document") if isinstance(result["payload"], dict) else None
        if isinstance(doc, str) and len(doc) > max_chars:
            result["payload"]["document"] = doc[:max_chars]
            result["truncated"] = True
            result["total_chars"] = len(doc)
        return result

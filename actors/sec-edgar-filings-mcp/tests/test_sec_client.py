"""Unit tests for the SEC EDGAR Filings & XBRL Financials Actor."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sec_client import (  # noqa: E402
    SecEdgarClient,
    build_mcp_summary,
    build_sec_document_urls,
    decode_8k_items,
    format_cik_10,
    parse_xbrl_snapshot,
)


def test_cik_url_and_8k_decoder() -> None:
    """Verify CIK zero-padding, SEC Archive URL builder, and 8-K item decoder."""
    assert format_cik_10(320193) == "0000320193"
    assert format_cik_10("CIK0001045810") == "0001045810"

    doc_url, folder_url = build_sec_document_urls(
        "0000320193", "0000320193-26-000105", "aapl-20260926.htm"
    )
    assert folder_url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000105/"
    assert doc_url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000105/aapl-20260926.htm"

    coded, decoded = decode_8k_items(["2.02", "9.01"])
    assert coded == ["2.02", "9.01"]
    assert "Results of Operations and Financial Condition" in decoded
    assert "Financial Statements and Exhibits" in decoded


def test_xbrl_snapshot_prefers_latest_annual_across_tags() -> None:
    """Select newest 10-K FY revenue even when an older GAAP tag exists."""
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "start": "2017-10-01", "end": "2018-09-29", "val": 62900000000},
                        ]
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"form": "10-Q", "start": "2026-04-01", "end": "2026-06-27", "val": 95000000000},
                            {"form": "10-K", "start": "2026-06-28", "end": "2026-09-26", "val": 110000000000},  # <300d skipped
                            {"form": "10-K", "start": "2025-09-28", "end": "2026-09-26", "val": 400000000000},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "start": "2025-09-28", "end": "2026-09-26", "val": 100000000000},
                        ]
                    }
                },
                "Assets": {"units": {"USD": [{"form": "10-K", "end": "2026-09-26", "val": 350000000000}]}},
                "StockholdersEquity": {"units": {"USD": [{"form": "10-K", "end": "2026-09-26", "val": 80000000000}]}},
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [{"form": "10-K", "end": "2026-09-26", "val": 30000000000}]}
                },
            }
        }
    }

    snap = parse_xbrl_snapshot(payload, cik="0000320193", ticker="AAPL", company_name="Apple Inc.")
    assert snap.fiscalYearEndPeriod == "2026-09-26"
    assert snap.latestAnnualRevenueUsd == 400000000000.0
    assert snap.latestAnnualNetIncomeUsd == 100000000000.0
    assert snap.netProfitMarginPercent == 25.0
    assert snap.totalAssetsUsd == 350000000000.0
    assert snap.stockholdersEquityUsd == 80000000000.0
    assert snap.cashAndEquivalentsUsd == 30000000000.0


def test_sec_client_end_to_end_and_mcp_summary() -> None:
    """Mocked SEC submissions + XBRL companyfacts produce enriched filings and summary."""
    submissions_mock = {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "tickers": ["AAPL"],
        "filings": {
            "recent": {
                "form": ["4", "8-K", "10-K"],
                "filingDate": ["2026-11-19", "2026-10-30", "2026-10-29"],
                "reportDate": ["2026-11-18", "2026-10-30", "2026-09-26"],
                "accessionNumber": ["0001-26-01", "0002-26-02", "0003-26-03"],
                "primaryDocument": ["form4.xml", "ea8k.htm", "aapl-10k.htm"],
                "primaryDocDescription": ["FORM 4", "8-K", "10-K"],
                "items": ["", "2.02,9.01", ""],
                "isInlineXBRL": [0, 1, 1],
            }
        },
    }
    facts_mock = {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [{"form": "10-K", "start": "2025-09-28", "end": "2026-09-26", "val": 400000000000}]}},
                "NetIncomeLoss": {"units": {"USD": [{"form": "10-K", "start": "2025-09-28", "end": "2026-09-26", "val": 100000000000}]}},
            }
        }
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if "/submissions/" in request.url.path:
            return httpx.Response(200, json=submissions_mock)
        if "/companyfacts/" in request.url.path:
            return httpx.Response(200, json=facts_mock)
        return httpx.Response(404)

    async def _run() -> None:
        async with SecEdgarClient() as client:
            await client.close()
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            records, snapshots = await client.search_filings(
                tickers_or_ciks=["AAPL"],
                forms=["10-K", "8-K"],
                include_financial_snapshot=True,
                max_filings_per_company=5,
            )

        assert len(records) == 2  # Form 4 excluded by forms filter
        assert records[0].form == "8-K"
        assert "Results of Operations and Financial Condition" in records[0].items8KDecoded
        assert records[0].latestAnnualRevenueUsd == 400000000000.0
        assert len(snapshots) == 1

        summary = build_mcp_summary(records, snapshots, {"tickers": ["AAPL"]})
        assert summary["status"] == "OK"
        assert summary["metrics"]["companies_analyzed"] == 1
        assert summary["metrics"]["total_filings_returned"] == 2

    asyncio.run(_run())

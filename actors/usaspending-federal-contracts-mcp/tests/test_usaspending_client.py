"""Unit tests for USAspending Federal Contracts & Re-Compete Radar client."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx
import pytest

from src.usaspending_client import (
    UsaSpendingApiError,
    UsaSpendingClient,
    build_mcp_summary,
    build_search_payload,
    classify_recompete,
)


def test_classify_recompete_buckets() -> None:
    ref = date(2026, 11, 24)
    assert classify_recompete("2026-12-10", reference_date=ref) == (16, "URGENT_RECOMPETE")
    assert classify_recompete("2027-07-01", reference_date=ref) == (219, "UPCOMING_RECOMPETE")
    assert classify_recompete("2029-01-01", reference_date=ref) == (769, "ACTIVE_LONG_TERM")
    assert classify_recompete("2025-05-01", reference_date=ref) == (-572, "EXPIRED")
    assert classify_recompete(None, reference_date=ref) == (None, "UNKNOWN")


def test_build_search_payload_filters() -> None:
    payload = build_search_payload(
        keywords=["cybersecurity"],
        recipient_names=["BOOZ ALLEN"],
        naics_codes=["541512"],
        awarding_agency="Department of Defense",
        place_of_performance_state="va",
        award_type="contracts",
        min_award_amount_usd=1_000_000,
        limit=25,
        page=2,
    )
    filters = payload["filters"]
    assert filters["award_type_codes"] == ["A", "B", "C", "D"]
    assert filters["keywords"] == ["cybersecurity"]
    assert filters["recipient_search_text"] == ["BOOZ ALLEN"]
    assert filters["naics_codes"] == {"require": ["541512"]}
    assert filters["agencies"] == [
        {"type": "awarding", "tier": "toptier", "name": "Department of Defense"}
    ]
    assert filters["place_of_performance_locations"] == [{"country": "USA", "state": "VA"}]
    assert filters["award_amounts"] == [{"lower_bound": 1_000_000.0}]
    assert payload["page"] == 2


def test_search_awards_paginates_filters_expiring_and_builds_summary() -> None:
    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        page = body["page"]
        seen_pages.append(page)
        if page == 1:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "Award ID": "AWD-URGENT",
                            "Recipient Name": "ALPHA GOV INC",
                            "Start Date": "2023-01-01",
                            "End Date": "2027-01-15",
                            "Award Amount": 5000000.0,
                            "Awarding Agency": "Department of Defense",
                            "Awarding Sub Agency": "Air Force",
                            "Description": "Zero trust cybersecurity support",
                            "Place of Performance State Code": "VA",
                            "generated_internal_id": "CONT_AWD_1",
                        },
                        {
                            "Award ID": "AWD-LATER",
                            "Recipient Name": "BETA TECH LLC",
                            "Start Date": "2024-01-01",
                            "End Date": "2029-06-01",
                            "Award Amount": 9000000.0,
                            "Awarding Agency": "General Services Administration",
                            "Awarding Sub Agency": "FAS",
                            "Description": "Long-term cloud migration",
                            "Place of Performance State Code": "MD",
                            "generated_internal_id": "CONT_AWD_2",
                        },
                    ],
                    "page_metadata": {"hasNext": True},
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "Award ID": "AWD-SOONER",
                        "Recipient Name": "ALPHA GOV INC",
                        "Start Date": "2022-05-01",
                        "End Date": "2026-12-05",
                        "Award Amount": 2500000.0,
                        "Awarding Agency": "Department of Defense",
                        "Awarding Sub Agency": "Army",
                        "Description": "SOC operations",
                        "Place of Performance State Code": "TX",
                        "generated_internal_id": "CONT_AWD_3",
                    }
                ],
                "page_metadata": {"hasNext": False},
            },
        )

    transport = httpx.MockTransport(handler)
    ref_date = date(2026, 11, 24)

    async def _run():
        async with UsaSpendingClient(transport=transport) as client:
            return await client.search_awards(
                keywords=["cybersecurity"],
                expiring_within_days=180,
                max_records=10,
                reference_date=ref_date,
            )

    records = asyncio.run(_run())
    assert seen_pages == [1, 2]
    assert [r.awardId for r in records] == ["AWD-SOONER", "AWD-URGENT"]
    assert records[0].awardUrl == "https://www.usaspending.gov/award/CONT_AWD_3"
    assert records[0].recompetePriority == "URGENT_RECOMPETE"

    summary = build_mcp_summary(records, {"keywords": ["cybersecurity"]})
    assert summary["status"] == "OK"
    assert summary["metrics"]["total_awards_returned"] == 2
    assert summary["metrics"]["total_award_value_usd"] == 7500000.0
    assert summary["metrics"]["urgent_recompete_count"] == 2
    assert summary["metrics"]["top_incumbents"][0]["recipient"] == "ALPHA GOV INC"


def test_search_awards_raises_on_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)

    async def _run():
        async with UsaSpendingClient(max_retries=0, transport=transport) as client:
            await client.search_awards(keywords=["cybersecurity"])

    with pytest.raises(UsaSpendingApiError, match="HTTP 500"):
        asyncio.run(_run())

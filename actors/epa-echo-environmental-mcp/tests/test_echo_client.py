"""Unit tests for EPA ECHO Client and MCP summary logic."""

from __future__ import annotations

import json
import httpx
import pytest

from src.echo_client import (
    EpaEchoClient,
    EpaFacility,
    _parse_currency,
    _parse_int,
    build_mcp_summary,
)


def test_parse_currency() -> None:
    assert _parse_currency("$0") == 0.0
    assert _parse_currency("$1,250.50") == 1250.50
    assert _parse_currency(None) == 0.0
    assert _parse_currency("invalid") == 0.0
    assert _parse_currency(500) == 500.0


def test_parse_int() -> None:
    assert _parse_int("42") == 42
    assert _parse_int(None, default=5) == 5
    assert _parse_int("bad", default=0) == 0


def test_epa_facility_from_raw_api() -> None:
    raw = {
        "RegistryID": "110071338212",
        "FacName": "TEST INDUSTRIAL FACILITY",
        "FacStreet": "100 PLANT ROAD",
        "FacCity": "HOUSTON",
        "FacState": "TX",
        "FacZip": "77001",
        "FacCounty": "HARRIS",
        "FacComplianceStatus": "Significant Violation",
        "FacSNCFlg": "Y",
        "FacQtrsWithNC": "4",
        "CAAComplianceStatus": "Violation",
        "CWAPermitTypes": "NPDES",
        "FacInspectionCount": "3",
        "FacFormalActionCount": "1",
        "FacTotalPenalties": "$25,000",
    }
    facility = EpaFacility.from_raw_api(raw)

    assert facility.registry_id == "110071338212"
    assert facility.facility_name == "TEST INDUSTRIAL FACILITY"
    assert facility.has_significant_non_compliance is True
    assert facility.quarters_in_non_compliance == 4
    assert facility.total_penalties == 25000.0
    assert facility.formal_enforcement_action_count == 1
    assert "CAA (Air)" in facility.active_programs
    assert "CWA (Water)" in facility.active_programs
    assert facility.echo_report_url == "https://echo.epa.gov/detailed-facility-report?fid=110071338212"


def test_build_mcp_summary_critical() -> None:
    facilities = [
        EpaFacility(
            registry_id="1",
            facility_name="FACILITY A",
            has_significant_non_compliance=True,
            total_penalties=15000.0,
            active_programs=["CAA (Air)"],
            echo_report_url="https://echo.epa.gov/1",
        ),
        EpaFacility(
            registry_id="2",
            facility_name="FACILITY B",
            has_significant_non_compliance=False,
            total_penalties=0.0,
            echo_report_url="https://echo.epa.gov/2",
        ),
    ]
    summary = build_mcp_summary(facilities, criteria={"state": "TX"})

    assert summary["risk_level"] == "CRITICAL"
    assert summary["metrics"]["total_facilities_analyzed"] == 2
    assert summary["metrics"]["facilities_with_significant_non_compliance"] == 1
    assert summary["metrics"]["total_penalties_assessed_usd"] == 15000.0
    assert len(summary["flagged_high_risk_facilities"]) == 1


def test_build_mcp_summary_low_risk() -> None:
    facilities = [
        EpaFacility(
            registry_id="1",
            facility_name="CLEAN FACILITY",
            compliance_status="No Violation Identified",
            has_significant_non_compliance=False,
            quarters_in_non_compliance=0,
            total_penalties=0.0,
            formal_enforcement_action_count=0,
            echo_report_url="https://echo.epa.gov/1",
        )
    ]
    summary = build_mcp_summary(facilities, criteria={"state": "OH"})
    assert summary["risk_level"] == "LOW"
    assert summary["metrics"]["facilities_with_significant_non_compliance"] == 0
    assert summary["metrics"]["total_penalties_assessed_usd"] == 0.0


def test_search_facilities_flow() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "get_facilities" in url_str:
            return httpx.Response(
                200,
                json={
                    "Results": {
                        "QueryRows": "2",
                        "QueryID": "999",
                    }
                },
            )
        if "get_qid" in url_str:
            return httpx.Response(
                200,
                json={
                    "Results": {
                        "TotalPages": "1",
                        "Facilities": [
                            {
                                "RegistryID": "1001",
                                "FacName": "ALPHA CHEMICAL",
                                "FacState": "TX",
                                "FacSNCFlg": "N",
                            },
                            {
                                "RegistryID": "1002",
                                "FacName": "BETA REFINERY",
                                "FacState": "TX",
                                "FacSNCFlg": "Y",
                            },
                        ],
                    }
                },
            )
        return httpx.Response(404)

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        async with EpaEchoClient(transport=transport) as client:
            facilities = await client.search_facilities(state="TX", max_records=10)

        assert len(facilities) == 2
        assert facilities[0].facility_name == "ALPHA CHEMICAL"
        assert facilities[1].has_significant_non_compliance is True

    import asyncio
    asyncio.run(_run())


def test_search_facilities_zero_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"Results": {"QueryRows": "0", "QueryID": None}},
        )

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        async with EpaEchoClient(transport=transport) as client:
            facilities = await client.search_facilities(state="WY", max_records=10)

        assert facilities == []

    import asyncio
    asyncio.run(_run())


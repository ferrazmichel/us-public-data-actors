"""Unit tests for the openFDA Drug, Device & Food Recall Radar Actor."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.openfda_client import (  # noqa: E402
    OpenFdaClient,
    build_lucene_search,
    build_mcp_summary,
    classify_recall_risk,
    normalize_fda_date,
)


def test_date_formatting_and_lucene_builder() -> None:
    """Verify FDA YYYYMMDD parsing and Lucene query assembly."""
    assert normalize_fda_date("20260815") == "2026-08-15"
    assert normalize_fda_date("2026-08-15") == "2026-08-15"
    assert normalize_fda_date("") is None

    expr = build_lucene_search(
        search_query="pacemaker",
        recalling_firm="Medtronic",
        classification="Class I",
        status="Ongoing",
        state="MN",
        report_date_from="2026-01-01",
    )
    assert expr is not None
    assert 'classification:"Class I"' in expr
    assert 'status:"Ongoing"' in expr
    assert 'recalling_firm:"Medtronic"' in expr
    assert 'state:"MN"' in expr
    assert "report_date:[20260101 TO 20991231]" in expr
    assert 'product_description:"pacemaker"' in expr

    assert build_lucene_search(classification="ALL", status="ALL") is None


def test_risk_level_classification() -> None:
    """Verify Class I/II/III risk levels match severity, ongoing status, and distribution."""
    assert (
        classify_recall_risk(classification="Class I", status="Ongoing") == "CRITICAL"
    )
    assert (
        classify_recall_risk(classification="Class I", status="Terminated") == "HIGH"
    )
    assert (
        classify_recall_risk(
            classification="Class II",
            status="Ongoing",
            distribution_pattern="Nationwide in US",
        )
        == "HIGH"
    )
    assert (
        classify_recall_risk(
            classification="Class II",
            status="Terminated",
            distribution_pattern="TX only",
        )
        == "MODERATE"
    )
    assert classify_recall_risk(classification="Class III", status="Ongoing") == "LOW"


def test_multi_domain_merge_404_handling_and_mcp_summary() -> None:
    """Verify `all` domains merge cleanly, sort descending, handle 404, and generate summary."""

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/drug/" in path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "recall_number": "D-001-2026",
                            "event_id": "99001",
                            "classification": "Class I",
                            "status": "Ongoing",
                            "voluntary_mandated": "Voluntary: Firm initiated",
                            "recalling_firm": "Acme Pharma LLC",
                            "state": "NJ",
                            "country": "United States",
                            "report_date": "20261110",
                            "recall_initiation_date": "20261101",
                            "product_description": "Sterile Vial 10 mL",
                            "reason_for_recall": "Potential fungal contamination",
                            "distribution_pattern": "Nationwide",
                            "openfda": {"brand_name": ["ACME STERILE"], "product_ndc": ["12345-678"]},
                        }
                    ]
                },
            )
        if "/device/" in path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "recall_number": "Z-100-2026",
                            "event_id": "99002",
                            "classification": "Class II",
                            "status": "Ongoing",
                            "voluntary_mandated": "Voluntary: Firm initiated",
                            "recalling_firm": "MedDevice Corp",
                            "state": "CA",
                            "country": "United States",
                            "report_date": "20261115",
                            "recall_initiation_date": "20261105",
                            "product_description": "Infusion Pump Model X",
                            "reason_for_recall": "Battery alarm software bug",
                            "distribution_pattern": "CA, AZ",
                            "openfda": {"device_name": ["Infusion Pump"]},
                        }
                    ]
                },
            )
        # Food returns openFDA 404 NOT_FOUND for 0 matches
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}})

    async def _run() -> None:
        async with OpenFdaClient() as client:
            await client.close()
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            recalls = await client.search_recalls(domain="all", classification="ALL", status="ALL", max_records=10)

        assert len(recalls) == 2
        # Sorted by reportDate descending -> Z-100-2026 (2026-11-15) before D-001-2026 (2026-11-10)
        assert recalls[0].recallNumber == "Z-100-2026"
        assert recalls[0].domain == "device"
        assert recalls[0].riskLevel == "MODERATE"
        assert recalls[1].recallNumber == "D-001-2026"
        assert recalls[1].domain == "drug"
        assert recalls[1].riskLevel == "CRITICAL"
        assert recalls[1].brandNames == ["ACME STERILE"]

        summary = build_mcp_summary(recalls, {"domain": "all"})
        assert summary["overall_alert_level"] == "CRITICAL_RECALLS_DETECTED"
        assert summary["metrics"]["total_recalls"] == 2
        assert summary["metrics"]["domain_breakdown"] == {"device": 1, "drug": 1}

    asyncio.run(_run())

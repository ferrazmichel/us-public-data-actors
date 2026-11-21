"""Unit tests for the USITC HTS Tariff & Landed Cost Calculator Actor."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.hts_client import (  # noqa: E402
    MPF_INFORMAL_USD,
    MPF_MAX_USD,
    MPF_MIN_USD,
    HtsClient,
    build_mcp_summary,
    calculate_landed_cost,
    parse_ad_valorem_percent,
    parse_special_programs,
)


def test_parse_ad_valorem_and_special_programs() -> None:
    """Parser handles Free, standard %, compound rates, and FTA SPI tokens."""
    assert parse_ad_valorem_percent("Free") == (0.0, False)
    assert parse_ad_valorem_percent("3.4%") == (3.4, False)
    assert parse_ad_valorem_percent("5% + 1.2¢/kg") == (5.0, True)
    assert parse_ad_valorem_percent("12¢/doz") == (0.0, True)

    free_spis, reduced_spis = parse_special_programs(
        "Free (A,AU,BH,CL,CO,IL,JO,KR,MA,OM,P,PA,PE,S,SG) 1.5% (JP)"
    )
    assert {"S", "KR", "AU", "SG", "IL"}.issubset(free_spis)
    assert reduced_spis == {"JP": 1.5}


def test_calculate_landed_cost_mpf_hmf_and_fta_rules() -> None:
    """Verify China Section 301, USMCA duty+MPF exemption, Column 2, informal & max MPF."""
    special = "Free (A,AU,BH,CL,CO,IL,JO,KR,MA,OM,P,PA,PE,S,SG)"

    # 1. China lithium-ion batteries ($25,000 ocean) -> 3.4% base + 25% Sec 301 + MPF 0.3464% + HMF 0.125%
    cn = calculate_landed_cost(
        htsno="8507.60.00.10",
        general_text="3.4%",
        special_text=special,
        other_text="40%",
        origin="CN",
        shipment_value_usd=25000.0,
        freight_usd=1200.0,
        transport_mode="ocean",
    )
    assert cn.baseDutyPercent == 3.4
    assert cn.baseDutyUsd == 850.0
    assert cn.additionalTariffPercent == 25.0
    assert cn.additionalTariffUsd == 6250.0
    assert cn.mpfFeeUsd == 86.6  # 25000 * 0.003464
    assert cn.hmfFeeUsd == 31.25  # 25000 * 0.00125
    assert cn.totalDutiesAndFeesUsd == 7217.85
    assert cn.totalLandedCostUsd == 33417.85

    # 2. Mexico (USMCA 'S') -> 0% base, 0% additional, $0 MPF, $0 HMF on truck!
    mx = calculate_landed_cost(
        htsno="8507.60.00.10",
        general_text="3.4%",
        special_text=special,
        other_text="40%",
        origin="MX",
        shipment_value_usd=25000.0,
        freight_usd=1200.0,
        transport_mode="truck",
    )
    assert mx.ftaExempt is True
    assert mx.mpfExempt is True
    assert mx.baseDutyUsd == 0.0
    assert mx.mpfFeeUsd == 0.0
    assert mx.hmfFeeUsd == 0.0
    assert mx.totalDutiesAndFeesUsd == 0.0
    assert mx.totalLandedCostUsd == 26200.0

    # 3. Column 2 embargoed country (RU) -> 40% other rate
    ru = calculate_landed_cost(
        htsno="8507.60.00.10",
        general_text="3.4%",
        special_text=special,
        other_text="40%",
        origin="RU",
        shipment_value_usd=10000.0,
        freight_usd=0.0,
        transport_mode="air",
    )
    assert ru.baseDutyPercent == 40.0
    assert ru.baseDutyUsd == 4000.0
    assert ru.mpfFeeUsd == 34.64
    assert ru.hmfFeeUsd == 0.0

    # 4. MPF bounds: informal ($1,000), formal min ($3,000), formal max ($300,000)
    informal = calculate_landed_cost(
        htsno="8507.60.00",
        general_text="3.4%",
        special_text="",
        other_text="",
        origin="DE",
        shipment_value_usd=1000.0,
        freight_usd=0.0,
        transport_mode="air",
    )
    assert informal.mpfFeeUsd == MPF_INFORMAL_USD

    low_formal = calculate_landed_cost(
        htsno="8507.60.00",
        general_text="3.4%",
        special_text="",
        other_text="",
        origin="DE",
        shipment_value_usd=3000.0,
        freight_usd=0.0,
        transport_mode="air",
    )
    assert low_formal.mpfFeeUsd == MPF_MIN_USD

    high_formal = calculate_landed_cost(
        htsno="8507.60.00",
        general_text="3.4%",
        special_text="",
        other_text="",
        origin="DE",
        shipment_value_usd=300000.0,
        freight_usd=0.0,
        transport_mode="air",
    )
    assert high_formal.mpfFeeUsd == MPF_MAX_USD


def test_hierarchical_rate_inheritance_and_mcp_summary() -> None:
    """10-digit statistical lookup fetches 6-digit heading tree, inherits 8-digit rate, and compares countries."""
    requested_keywords: list[str] = []

    sample_rows: list[dict[str, Any]] = [
        {
            "htsno": "8507.60.00",
            "indent": "1",
            "description": "Lithium-ion batteries",
            "general": "3.4%",
            "special": "Free (A,AU,BH,CL,CO,IL,JO,KR,MA,OM,P,PA,PE,S,SG)",
            "other": "40%",
            "units": [],
            "footnotes": [],
        },
        {
            "htsno": "8507.60.00.10",
            "indent": "2",
            "description": "Of a kind used as the primary source of electrical power for EVs",
            "general": "",
            "special": "",
            "other": "",
            "units": ["No.", "kg"],
            "footnotes": [],
        },
        {
            "htsno": "9902.16.20",
            "indent": "0",
            "description": "Rechargeable lithium batteries with polymer electrolyte",
            "general": "Free",
            "special": "No change",
            "other": "No change",
            "units": [],
            "footnotes": [{"value": "See chapter 99 statistical note 1."}],
        },
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_keywords.append(request.url.params.get("keyword", ""))
        return httpx.Response(200, json=sample_rows)

    async def _run() -> None:
        async with HtsClient() as client:
            await client.close()
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            records = await client.search_and_calculate(
                query="8507.60.00.10",
                country_of_origin="CN",
                compare_countries=["CN", "VN", "MX", "KR"],
                shipment_value_usd=25000.0,
                freight_and_insurance_usd=1200.0,
                transport_mode="ocean",
            )

        # Must have normalized 10-digit query to 6-digit prefix so parent 8507.60.00 arrived
        assert requested_keywords == ["8507.60"]
        # Filtered down strictly to the requested 10-digit line (Chapter 99 attached as metadata)
        assert len(records) == 1
        rec = records[0]
        assert rec.htsno == "8507.60.00.10"
        assert rec.inheritedRateFromHtsNo == "8507.60.00"
        assert rec.generalRateText == "3.4%"
        assert rec.baseDutyPercent == 3.4
        assert rec.additionalTariffPercent == 25.0
        assert len(rec.chapter99References) == 1
        assert rec.chapter99References[0].htsno == "9902.16.20"
        assert rec.bestAlternativeCountry in {"MX", "KR"}
        assert rec.maxSourcingSavingsUsd > 6000.0

        summary = build_mcp_summary(records, {"query": "8507.60.00.10", "origin": "CN"})
        assert summary["status"] == "OK"
        assert summary["metrics"]["total_hts_lines_evaluated"] == 1
        assert summary["items"][0]["inherited_from"] == "8507.60.00"

    asyncio.run(_run())

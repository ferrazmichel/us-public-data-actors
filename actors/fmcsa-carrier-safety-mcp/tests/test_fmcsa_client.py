"""Unit tests for FMCSA/USDOT client, vetting rules, and MCP summary."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from src.fmcsa_client import (
    FmcsaCarrier,
    FmcsaClient,
    _clean_digits,
    _escape_soql,
    _extract_cargo_types,
    _format_yyyymmdd,
    build_mcp_summary,
    evaluate_carrier_risk,
)


def test_helpers_and_cargo_extraction() -> None:
    assert _clean_digits("MC-00202830") == "202830"
    assert _clean_digits("00022105") == "22105"
    assert _clean_digits("USDOT 000") == "0"
    assert _clean_digits(None) == ""

    assert _escape_soql("O'REILLY") == "O''REILLY"
    assert _format_yyyymmdd("20261118") == "2026-11-18"
    assert _format_yyyymmdd("2026-11-18") == "2026-11-18"
    assert _format_yyyymmdd("") is None

    cargo = _extract_cargo_types(
        {
            "crgo_genfreight": "X",
            "crgo_coldfood": "X",
            "crgo_cargoothr": "X",
            "crgo_cargoothr_desc": "STEEL COILS",
        }
    )
    assert cargo == ["General Freight", "Refrigerated Food", "STEEL COILS"]


def test_evaluate_carrier_risk_verdicts() -> None:
    base = FmcsaCarrier.from_census_row(
        {
            "dot_number": "22105",
            "legal_name": "SAFE TRUCKING INC",
            "status_code": "A",
            "add_date": "20100101",
            "safety_rating": "S",
            "classdef": "AUTHORIZED FOR HIRE",
            "power_units": "25",
            "total_drivers": "30",
        }
    )
    base.authority_checked = True
    base.common_authority_status = "A"
    base.bipd_required_usd = 750_000
    base.bipd_on_file_usd = 1_000_000
    evaluate_carrier_risk(base, reference_date=date(2026, 11, 21))
    assert base.vetting_verdict == "PASS"
    assert base.risk_flags == []

    # Caution: new authority (< 90 days)
    new_auth = base.model_copy(deep=True)
    new_auth.add_date = "2026-10-15"
    evaluate_carrier_risk(new_auth, reference_date=date(2026, 11, 21))
    assert new_auth.vetting_verdict == "CAUTION"
    assert any("90 days" in flag for flag in new_auth.risk_flags)

    # High risk: BIPD below required minimum & Conditional rating
    underinsured = base.model_copy(deep=True)
    underinsured.safety_rating = "Conditional"
    underinsured.bipd_on_file_usd = 300_000
    evaluate_carrier_risk(underinsured, reference_date=date(2026, 11, 21))
    assert underinsured.vetting_verdict == "HIGH_RISK"
    assert len(underinsured.risk_flags) == 2

    # Do not use: pending revocation or inactive status
    revoked = base.model_copy(deep=True)
    revoked.pending_revocation = True
    evaluate_carrier_risk(revoked, reference_date=date(2026, 11, 21))
    assert revoked.vetting_verdict == "DO_NOT_USE"


def test_search_carriers_join_and_memory_fleet_filter() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        seen_urls.append(url_str)
        if "az4n-8mr2.json" in url_str:
            assert "::number" not in url_str
            return httpx.Response(
                200,
                json=[
                    {
                        "dot_number": "22105",
                        "docket1prefix": "MC",
                        "docket1": "202830",
                        "legal_name": "LONE STAR FREIGHT LLC",
                        "status_code": "A",
                        "add_date": "20200110",
                        "phy_state": "TX",
                        "power_units": "12",
                        "total_drivers": "15",
                        "hm_ind": "N",
                        "classdef": "AUTHORIZED FOR HIRE",
                    },
                    {
                        "dot_number": "99999",
                        "legal_name": "TINY OWNER OP",
                        "status_code": "A",
                        "add_date": "20240101",
                        "phy_state": "TX",
                        "power_units": "1",
                        "total_drivers": "1",
                    },
                ],
            )
        if "6eyk-hxee.json" in url_str:
            assert "00022105" in url_str
            return httpx.Response(
                200,
                json=[
                    {
                        "dot_number": "00022105",
                        "docket_number": "MC202830",
                        "common_stat": "A",
                        "contract_stat": "N",
                        "broker_stat": "N",
                        "common_rev_pend": "N",
                        "min_cov_amount": "00750",
                        "bipd_file": "01000",
                        "cargo_file": "Y",
                        "bond_file": "N",
                    }
                ],
            )
        if "qh9u-swkp.json" in url_str:
            assert "00022105" in url_str
            return httpx.Response(
                200,
                json=[
                    {
                        "dot_number": "00022105",
                        "docket_number": "MC202830",
                        "ins_form_code": "91X",
                        "mod_col_1": "BIPD/Primary",
                        "name_company": "PROGRESSIVE COMMERCIAL",
                        "policy_no": "CA123456",
                        "max_cov_amount": "1000",
                        "underl_lim_amount": "0",
                        "effective_date": "01/01/2026",
                    }
                ],
            )
        return httpx.Response(404)

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        async with FmcsaClient(transport=transport) as client:
            carriers = await client.search_carriers(
                state="TX",
                min_power_units=5,
                include_authority_and_insurance=True,
                max_records=10,
            )

        assert len(carriers) == 1
        c = carriers[0]
        assert c.dot_number == "22105"
        assert c.mc_number == "MC-202830"
        assert c.common_authority_status == "A"
        assert c.bipd_required_usd == 750_000
        assert c.bipd_on_file_usd == 1_000_000
        assert c.cargo_insurance_on_file is True
        assert len(c.active_insurers) == 1
        assert c.active_insurers[0].insurer_name == "PROGRESSIVE COMMERCIAL"
        assert c.vetting_verdict == "PASS"

    asyncio.run(_run())


def test_search_carriers_zero_results_and_mcp_summary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        async with FmcsaClient(transport=transport) as client:
            carriers = await client.search_carriers(dot_number="999999999")
        assert carriers == []

    asyncio.run(_run())

    empty_summary = build_mcp_summary([], criteria={"dot_number": "999999999"})
    assert empty_summary["overall_vetting_status"] == "NO_CARRIERS_FOUND"
    assert empty_summary["metrics"]["total_carriers_analyzed"] == 0

    flagged_carrier = FmcsaCarrier.from_census_row(
        {
            "dot_number": "55555",
            "legal_name": "RISKY HAULING LLC",
            "status_code": "I",
            "phy_state": "OH",
            "power_units": "4",
            "total_drivers": "5",
            "hm_ind": "Y",
        }
    )
    summary = build_mcp_summary([flagged_carrier], criteria={"state": "OH"})
    assert summary["overall_vetting_status"] == "DO_NOT_USE_FLAGGED"
    assert summary["metrics"]["verdict_breakdown"]["DO_NOT_USE"] == 1
    assert summary["metrics"]["total_power_units"] == 4
    assert summary["metrics"]["hazmat_authorized_carriers"] == 1
    assert len(summary["flagged_carriers"]) == 1

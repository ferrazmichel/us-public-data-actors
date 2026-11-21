"""Unit tests for the US 1099-NEC $2,000 Threshold & State Compliance Engine."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.compliance_engine import (  # noqa: E402
    US_STATES_1099_RULES,
    build_mcp_summary,
    evaluate_1099_compliance,
)


def test_all_51_us_jurisdictions_present_and_valid() -> None:
    """Dataset must cover all 50 US states plus Washington, DC."""
    assert len(US_STATES_1099_RULES) == 51
    assert {"CA", "NY", "TX", "FL", "PA", "MA", "NJ", "DC", "WY"}.issubset(
        US_STATES_1099_RULES.keys()
    )
    for code, rule in US_STATES_1099_RULES.items():
        assert len(code) == 2
        assert rule.stateName
        assert rule.stateAgencyName


def test_2026_state_only_filing_trap_at_1250_usd() -> None:
    """$1,250 in 2026 skips Federal ($2,000) but triggers direct state filing in $600/$1,000 states."""
    for state in ("CA", "PA", "MA", "NJ"):
        rec = evaluate_1099_compliance(
            scenario_label=f"Test {state}",
            state_code=state,
            tax_year=2026,
            payment_amount_usd=1250.0,
        )
        assert rec.complianceVerdict == "STATE_ONLY_FILING_TRAP"
        assert rec.federalFilingRequired is False
        assert rec.federalThresholdUsd == 2000.0
        assert rec.stateFilingRequired is True
        assert rec.directStatePortalRequired is True

    # TX/FL (no state tax) and NY/IL (federal-conforming) require no filing at $1,250 in 2026
    for state in ("TX", "FL", "NY", "IL"):
        rec = evaluate_1099_compliance(
            scenario_label=f"Test {state}",
            state_code=state,
            tax_year=2026,
            payment_amount_usd=1250.0,
        )
        assert rec.complianceVerdict == "NO_FILING_REQUIRED"
        assert rec.federalFilingRequired is False
        assert rec.stateFilingRequired is False

    # Same $1,250 in 2025 ($600 Federal threshold) required Federal filing in NY and TX!
    ny_2025 = evaluate_1099_compliance(
        scenario_label="NY 2025",
        state_code="NY",
        tax_year=2025,
        payment_amount_usd=1250.0,
    )
    assert ny_2025.complianceVerdict == "FEDERAL_AND_STATE_FILING_REQUIRED"
    assert ny_2025.federalThresholdUsd == 600.0


def test_2500_usd_federal_and_state_obligations() -> None:
    """$2,500 in 2026 triggers Federal filing everywhere plus State filing where applicable."""
    ca = evaluate_1099_compliance(
        scenario_label="CA $2500",
        state_code="CA",
        tax_year=2026,
        payment_amount_usd=2500.0,
    )
    assert ca.complianceVerdict == "FEDERAL_AND_STATE_FILING_REQUIRED"
    assert ca.federalFilingRequired is True
    assert ca.stateFilingRequired is True
    assert ca.maxIrsPenaltyRiskUsd == 660.0

    tx = evaluate_1099_compliance(
        scenario_label="TX $2500",
        state_code="TX",
        tax_year=2026,
        payment_amount_usd=2500.0,
    )
    assert tx.complianceVerdict == "FEDERAL_ONLY_FILING_REQUIRED"
    assert tx.federalFilingRequired is True
    assert tx.stateFilingRequired is False


def test_entity_credit_card_and_attorney_exceptions() -> None:
    """Verify § 6050W credit card exemption, C-Corp exemption, and Attorney override."""
    card = evaluate_1099_compliance(
        scenario_label="Card",
        state_code="CA",
        payment_amount_usd=5000.0,
        payment_method="credit_card_1099k",
    )
    assert card.complianceVerdict == "EXEMPT_1099K_PAYMENT_CARD"
    assert card.federalFilingRequired is False
    assert card.stateFilingRequired is False

    corp = evaluate_1099_compliance(
        scenario_label="Acme Inc.",
        state_code="CA",
        payment_amount_usd=5000.0,
        entity_type="c_corp",
        is_attorney_or_legal_services=False,
    )
    assert corp.complianceVerdict == "EXEMPT_CORPORATION"
    assert corp.federalFilingRequired is False

    law_firm = evaluate_1099_compliance(
        scenario_label="Smith Law PC",
        state_code="CA",
        payment_amount_usd=5000.0,
        entity_type="c_corp",
        is_attorney_or_legal_services=True,
    )
    assert law_firm.complianceVerdict == "FEDERAL_AND_STATE_FILING_REQUIRED"
    assert law_firm.federalFilingRequired is True
    assert law_firm.stateFilingRequired is True


def test_missing_w9_triggers_24_percent_backup_withholding_and_mcp_summary() -> None:
    """Missing W-9 triggers 24% Federal + state backup withholding and $0.01 mandatory filing."""
    ca_missing = evaluate_1099_compliance(
        scenario_label="No W9 Vendor",
        state_code="CA",
        tax_year=2026,
        payment_amount_usd=400.0,  # Below $2,000 AND below $600!
        w9_verified=False,
    )
    assert ca_missing.complianceVerdict == "CRITICAL_BACKUP_WITHHOLDING_REQUIRED"
    assert ca_missing.federalBackupWithholdingRequired is True
    assert ca_missing.federalBackupWithholdingUsd == 96.0  # 24% of $400
    assert ca_missing.stateBackupWithholdingUsd == 28.0    # 7% CA rate on $400
    assert ca_missing.totalBackupWithholdingUsd == 124.0
    assert ca_missing.federalFilingRequired is True
    assert ca_missing.stateFilingRequired is True

    summary = build_mcp_summary([ca_missing], {"tax_year": 2026})
    assert summary["federal_1099_nec_threshold_usd"] == 2000.0
    assert summary["metrics"]["total_backup_withholding_liability_usd"] == 124.0
    assert len(summary["critical_backup_withholding_alerts"]) == 1

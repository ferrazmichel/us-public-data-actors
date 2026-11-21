"""US Form 1099-NEC 2026 ($2,000 Federal vs. State Rules) & Backup Withholding Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

EntityType = Literal[
    "individual_sole_prop",
    "single_member_llc",
    "partnership_llc",
    "c_corp",
    "s_corp",
    "nonprofit",
]
PaymentMethod = Literal["ach_wire_check_cash", "credit_card_1099k"]
ThresholdMode = Literal["NO_STATE_1099_NEC", "FIXED_600_STATUTORY", "FOLLOWS_FEDERAL_THRESHOLD"]

FEDERAL_BACKUP_WITHHOLDING_RATE = 0.24
EXEMPT_CORPORATE_ENTITIES = {"c_corp", "s_corp", "nonprofit"}

# 2026 IRS IRC § 6721 penalty tiers per late/incorrect Form 1099-NEC
IRS_PENALTY_TIERS_USD = {
    "within_30_days": 60.0,
    "by_aug_1": 130.0,
    "after_aug_1_or_unfiled": 330.0,
    "intentional_disregard": 660.0,
}


@dataclass(frozen=True)
class State1099Rule:
    """State-level Form 1099-NEC reporting and backup withholding rule."""

    stateCode: str
    stateName: str
    hasStateIncomeTax: bool
    thresholdMode2026: ThresholdMode
    stateThreshold2026Usd: float | None
    cfsfParticipantForNec: bool
    stateAgencyName: str
    stateDueDate2026: str
    stateBackupWithholdingPercent: float = 0.0
    notes: str = ""


def _build_state_rules() -> dict[str, State1099Rule]:
    """Build complete 50-state + DC 2026 Form 1099-NEC rules registry."""
    raw_specs: list[State1099Rule] = [
        # --- 9 No State 1099-NEC Filing States ---
        State1099Rule("AK", "Alaska", False, "NO_STATE_1099_NEC", None, False, "Alaska Dept. of Revenue", "None", 0.0, "No state personal income tax or state 1099-NEC requirement."),
        State1099Rule("FL", "Florida", False, "NO_STATE_1099_NEC", None, False, "Florida Dept. of Revenue", "None", 0.0, "No state personal income tax or state 1099-NEC filing."),
        State1099Rule("NH", "New Hampshire", False, "NO_STATE_1099_NEC", None, False, "NH Dept. of Revenue Administration", "None", 0.0, "No wage/earned income tax or state 1099-NEC filing."),
        State1099Rule("NV", "Nevada", False, "NO_STATE_1099_NEC", None, False, "Nevada Dept. of Taxation", "None", 0.0, "No state personal income tax or state 1099-NEC filing."),
        State1099Rule("SD", "South Dakota", False, "NO_STATE_1099_NEC", None, False, "South Dakota Dept. of Revenue", "None", 0.0, "No state personal income tax or state 1099-NEC filing."),
        State1099Rule("TN", "Tennessee", False, "NO_STATE_1099_NEC", None, False, "Tennessee Dept. of Revenue", "None", 0.0, "No state personal income tax or state 1099-NEC filing."),
        State1099Rule("TX", "Texas", False, "NO_STATE_1099_NEC", None, False, "Texas Comptroller", "None", 0.0, "No state personal income tax or state 1099-NEC filing."),
        State1099Rule("WA", "Washington", False, "NO_STATE_1099_NEC", None, False, "Washington Dept. of Revenue", "None", 0.0, "No state personal income tax or state 1099-NEC filing."),
        State1099Rule("WY", "Wyoming", False, "NO_STATE_1099_NEC", None, False, "Wyoming Dept. of Revenue", "None", 0.0, "No state personal income tax or state 1099-NEC filing."),

        # --- 20 Statutory / Independent State Threshold States (Trap vs. 2026 $2,000 Federal) ---
        State1099Rule("AR", "Arkansas", True, "FIXED_600_STATUTORY", 2500.0, True, "Arkansas DFA (ATAP)", "2027-02-01", 0.0, "Arkansas statutory 1099 reporting threshold is $2,500."),
        State1099Rule("CA", "California", True, "FIXED_600_STATUTORY", 600.0, True, "California FTB / EDD", "2027-02-01", 7.0, "CA retains $600 reporting + 7% nonresident withholding over $1,500; independent contractors also trigger DE-542."),
        State1099Rule("CT", "Connecticut", True, "FIXED_600_STATUTORY", 600.0, False, "Connecticut DRS (myconneCT)", "2027-02-01", 0.0, "Direct electronic filing to CT DRS required at $600+."),
        State1099Rule("DC", "District of Columbia", True, "FIXED_600_STATUTORY", 600.0, False, "DC OTR (MyTax.DC.gov)", "2027-02-01", 0.0, "Direct electronic filing to DC OTR required at $600+."),
        State1099Rule("DE", "Delaware", True, "FIXED_600_STATUTORY", 600.0, False, "Delaware Division of Revenue", "2027-02-01", 0.0, "Direct state submission of 1099-NEC required at $600+."),
        State1099Rule("MA", "Massachusetts", True, "FIXED_600_STATUTORY", 600.0, False, "Massachusetts DOR (MassTaxConnect)", "2027-02-01", 0.0, "Massachusetts enforces $600 state threshold via MassTaxConnect."),
        State1099Rule("MD", "Maryland", True, "FIXED_600_STATUTORY", 600.0, True, "Comptroller of Maryland (bFile)", "2027-02-01", 0.0, "Retains $600 state reporting; direct bFile upload required if MD tax withheld."),
        State1099Rule("ME", "Maine", True, "FIXED_600_STATUTORY", 600.0, True, "Maine Revenue Services", "2027-02-01", 5.0, "Maine enforces $600 threshold and 5% backup withholding if payee lacks valid TIN."),
        State1099Rule("MI", "Michigan", True, "FIXED_600_STATUTORY", 600.0, True, "Michigan Dept. of Treasury (MTO)", "2027-02-28", 0.0, "Michigan requires state 1099-NEC at $600+ when nexus/withholding applies."),
        State1099Rule("MN", "Minnesota", True, "FIXED_600_STATUTORY", 600.0, True, "Minnesota Dept. of Revenue", "2027-02-01", 6.25, "MN enforces $600 reporting and 6.25% nonresident/missing-TIN withholding rules."),
        State1099Rule("MO", "Missouri", True, "FIXED_600_STATUTORY", 1200.0, True, "Missouri Dept. of Revenue", "2027-02-28", 0.0, "Missouri statutory nonemployee reporting threshold is $1,200."),
        State1099Rule("MS", "Mississippi", True, "FIXED_600_STATUTORY", 600.0, True, "Mississippi Dept. of Revenue (TAP)", "2027-02-28", 0.0, "Mississippi retains $600 state 1099 reporting."),
        State1099Rule("MT", "Montana", True, "FIXED_600_STATUTORY", 600.0, True, "Montana Dept. of Revenue (TAP)", "2027-02-01", 0.0, "Montana retains $600 threshold and mineral/services reporting."),
        State1099Rule("NC", "North Carolina", True, "FIXED_600_STATUTORY", 600.0, False, "North Carolina DOR (eNC3)", "2027-02-01", 0.0, "NC does not rely solely on IRS CF/SF for 1099-NEC; file via eNC3 portal."),
        State1099Rule("NJ", "New Jersey", True, "FIXED_600_STATUTORY", 1000.0, False, "NJ Division of Taxation", "2027-02-15", 0.0, "New Jersey requires direct filing for payments of $1,000+."),
        State1099Rule("OR", "Oregon", True, "FIXED_600_STATUTORY", 600.0, False, "Oregon Dept. of Revenue (iWire)", "2027-02-01", 8.0, "Oregon requires mandatory direct iWire filing at $600+ (does not accept IRS CF/SF for 1099-NEC)."),
        State1099Rule("PA", "Pennsylvania", True, "FIXED_600_STATUTORY", 600.0, False, "PA Dept. of Revenue (myPATH)", "2027-02-01", 0.0, "PA requires direct myPATH filing at $600+ (strictly excludes CF/SF for 1099-NEC)."),
        State1099Rule("RI", "Rhode Island", True, "FIXED_600_STATUTORY", 600.0, False, "RI Division of Taxation", "2027-02-01", 0.0, "Rhode Island retains $600 direct filing threshold."),
        State1099Rule("VT", "Vermont", True, "FIXED_600_STATUTORY", 600.0, False, "Vermont Dept. of Taxes (myVTax)", "2027-02-01", 6.6, "VT requires direct filing at $600+ and 6.6% backup withholding when missing TIN."),
        State1099Rule("WI", "Wisconsin", True, "FIXED_600_STATUTORY", 600.0, False, "Wisconsin DOR (My Tax Account)", "2027-02-01", 0.0, "WI mandates direct filing at $600+ regardless of Federal CF/SF."),

        # --- 22 Federal-Conforming States ($2,000 in 2026 unless state tax withheld) ---
        State1099Rule("AL", "Alabama", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Alabama Dept. of Revenue (My Alabama Taxes)", "2027-02-01", 0.0, "Tracks federal 1099-NEC threshold or whenever Alabama tax is withheld."),
        State1099Rule("AZ", "Arizona", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Arizona Dept. of Revenue", "2027-02-01", 0.0, "State 1099-NEC required only when federal filing applies or AZ tax is withheld."),
        State1099Rule("CO", "Colorado", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Colorado Dept. of Revenue (Revenue Online)", "2027-02-01", 0.0, "Conforms to federal 1099-NEC requirement unless CO tax was withheld."),
        State1099Rule("GA", "Georgia", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Georgia Dept. of Revenue (GTC)", "2027-02-01", 0.0, "Conforms to federal 1099-NEC threshold via IRS CF/SF or GTC if GA tax withheld."),
        State1099Rule("HI", "Hawaii", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Hawaii Dept. of Taxation", "2027-02-28", 0.0, "Tracks federal Form 1099-NEC requirement."),
        State1099Rule("IA", "Iowa", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, False, "Iowa Dept. of Revenue (GovConnectIowa)", "2027-02-15", 0.0, "Follows federal filing threshold, but direct GovConnectIowa upload applies if filing."),
        State1099Rule("ID", "Idaho", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Idaho State Tax Commission", "2027-02-01", 0.0, "Conforms to federal 1099-NEC unless Idaho withholding occurred."),
        State1099Rule("IL", "Illinois", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, False, "Illinois Dept. of Revenue (MyTax Illinois)", "2027-03-15", 0.0, "Follows federal threshold; direct MyTax upload required when IL tax is withheld."),
        State1099Rule("IN", "Indiana", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Indiana Dept. of Revenue (INTIME)", "2027-02-01", 0.0, "Conforms to federal Form 1099-NEC threshold via CF/SF unless IN tax withheld."),
        State1099Rule("KS", "Kansas", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Kansas Dept. of Revenue", "2027-02-01", 0.0, "Conforms to federal 1099-NEC threshold via IRS CF/SF."),
        State1099Rule("KY", "Kentucky", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, False, "Kentucky Dept. of Revenue", "2027-02-01", 0.0, "Follows federal threshold; direct upload required if KY tax withheld."),
        State1099Rule("LA", "Louisiana", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Louisiana Dept. of Revenue (LaTAP)", "2027-02-28", 0.0, "Conforms to federal 1099-NEC requirement via CF/SF."),
        State1099Rule("ND", "North Dakota", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "ND Office of State Tax Commissioner", "2027-02-01", 0.0, "Conforms to federal 1099-NEC requirement via IRS CF/SF."),
        State1099Rule("NE", "Nebraska", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Nebraska Dept. of Revenue", "2027-02-01", 0.0, "Conforms to federal Form 1099-NEC reporting via CF/SF."),
        State1099Rule("NM", "New Mexico", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "NM Taxation & Revenue Dept.", "2027-02-28", 0.0, "Conforms to federal Form 1099-NEC reporting via CF/SF."),
        State1099Rule("NY", "New York", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "NY Dept. of Taxation and Finance", "2027-02-01", 0.0, "NY generally does not require 1099-NEC when no NY withholding occurred and follows federal rules."),
        State1099Rule("OH", "Ohio", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Ohio Dept. of Taxation", "2027-02-01", 0.0, "Follows federal Form 1099-NEC reporting unless Ohio tax withheld."),
        State1099Rule("OK", "Oklahoma", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "Oklahoma Tax Commission (OkTAP)", "2027-02-28", 0.0, "Tracks federal threshold via IRS CF/SF (special $750 royalties rule applies to 1099-MISC)."),
        State1099Rule("SC", "South Carolina", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, True, "South Carolina DOR (MyDORWAY)", "2027-02-01", 0.0, "Conforms to federal 1099-NEC threshold; CF/SF accepted when no SC withholding."),
        State1099Rule("UT", "Utah", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, False, "Utah State Tax Commission (TAP)", "2027-02-01", 0.0, "Tracks federal threshold; direct filing required if UT withholding occurred."),
        State1099Rule("VA", "Virginia", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, False, "Virginia Dept. of Taxation (Web Upload)", "2027-02-01", 0.0, "Tracks federal threshold; direct Web Upload required whenever VA tax is withheld."),
        State1099Rule("WV", "West Virginia", True, "FOLLOWS_FEDERAL_THRESHOLD", 2000.0, False, "WV State Tax Dept. (MyTaxes)", "2027-02-01", 0.0, "Tracks federal threshold; direct portal filing required for WV withholding."),
    ]
    return {rule.stateCode: rule for rule in raw_specs}


US_STATES_1099_RULES: dict[str, State1099Rule] = _build_state_rules()


class ComplianceEvaluationRecord(BaseModel):
    """Structured 1099-NEC compliance audit result for a contractor or state rule scenario."""

    contractorOrScenario: str
    contractorId: str | None = None
    taxYear: int
    stateCode: str
    stateName: str
    paymentAmountUsd: float
    entityType: EntityType
    paymentMethod: PaymentMethod
    w9Verified: bool
    isAttorneyOrLegalServices: bool

    complianceVerdict: str
    federalFilingRequired: bool
    federalThresholdUsd: float
    stateFilingRequired: bool
    stateThresholdUsd: float | None = None
    directStatePortalRequired: bool
    cfsfCoversNonWithholding: bool
    filingChannel: str

    federalBackupWithholdingRequired: bool
    federalBackupWithholdingUsd: float
    stateBackupWithholdingUsd: float
    stateTaxWithheldUsd: float
    totalBackupWithholdingUsd: float

    maxIrsPenaltyRiskUsd: float
    irsPenaltyTiersUsd: dict[str, float] = Field(default_factory=dict)
    federalDueDate: str
    stateDueDate: str
    stateAgencyName: str
    actionRequired: str
    ruleExplanation: str


def evaluate_1099_compliance(
    *,
    scenario_label: str,
    state_code: str,
    tax_year: int = 2026,
    payment_amount_usd: float = 1250.0,
    entity_type: EntityType = "individual_sole_prop",
    payment_method: PaymentMethod = "ach_wire_check_cash",
    w9_verified: bool = True,
    is_attorney_or_legal_services: bool = False,
    state_tax_withheld_usd: float = 0.0,
    contractor_id: str | None = None,
) -> ComplianceEvaluationRecord:
    """Evaluate Federal (2026 $2,000 vs. 2025 $600) and State Form 1099-NEC obligations."""
    code = state_code.strip().upper()
    rule = US_STATES_1099_RULES.get(code)
    if rule is None:
        raise ValueError(f"Unsupported US state code: {state_code!r}")

    federal_threshold = 2000.0 if tax_year >= 2026 else 600.0
    federal_due_date = f"{tax_year + 1}-02-01" if tax_year == 2026 else f"{tax_year + 1}-02-02"
    state_due_date = (
        rule.stateDueDate2026
        if tax_year == 2026 or rule.stateDueDate2026 == "None"
        else rule.stateDueDate2026.replace("2027-", f"{tax_year + 1}-")
    )

    if rule.thresholdMode2026 == "NO_STATE_1099_NEC":
        effective_state_threshold: float | None = None
    elif rule.thresholdMode2026 == "FOLLOWS_FEDERAL_THRESHOLD":
        effective_state_threshold = federal_threshold
    else:
        effective_state_threshold = rule.stateThreshold2026Usd

    # Rule 1: Credit Card / Third-Party Network (Form 1099-K) Exemption under IRC § 6050W
    if payment_method == "credit_card_1099k":
        return ComplianceEvaluationRecord(
            contractorOrScenario=scenario_label,
            contractorId=contractor_id,
            taxYear=tax_year,
            stateCode=rule.stateCode,
            stateName=rule.stateName,
            paymentAmountUsd=round(payment_amount_usd, 2),
            entityType=entity_type,
            paymentMethod=payment_method,
            w9Verified=w9_verified,
            isAttorneyOrLegalServices=is_attorney_or_legal_services,
            complianceVerdict="EXEMPT_1099K_PAYMENT_CARD",
            federalFilingRequired=False,
            federalThresholdUsd=federal_threshold,
            stateFilingRequired=False,
            stateThresholdUsd=effective_state_threshold,
            directStatePortalRequired=False,
            cfsfCoversNonWithholding=rule.cfsfParticipantForNec,
            filingChannel="None (IRC § 6050W 1099-K Exemption)",
            federalBackupWithholdingRequired=False,
            federalBackupWithholdingUsd=0.0,
            stateBackupWithholdingUsd=0.0,
            stateTaxWithheldUsd=round(state_tax_withheld_usd, 2),
            totalBackupWithholdingUsd=round(state_tax_withheld_usd, 2),
            maxIrsPenaltyRiskUsd=0.0,
            irsPenaltyTiersUsd={},
            federalDueDate=federal_due_date,
            stateDueDate=state_due_date,
            stateAgencyName=rule.stateAgencyName,
            actionRequired="Do NOT issue Form 1099-NEC; card processor reports on Form 1099-K.",
            ruleExplanation="IRC § 6050W excludes credit card and third-party payment network transactions from Form 1099-NEC to prevent duplicate IRS reporting.",
        )

    # Rule 2: Corporate Exemption (C-Corp / S-Corp / Nonprofit) unless Legal Services
    is_corp_exempt = (
        entity_type in EXEMPT_CORPORATE_ENTITIES
        and not is_attorney_or_legal_services
        and state_tax_withheld_usd == 0.0
    )
    if is_corp_exempt:
        return ComplianceEvaluationRecord(
            contractorOrScenario=scenario_label,
            contractorId=contractor_id,
            taxYear=tax_year,
            stateCode=rule.stateCode,
            stateName=rule.stateName,
            paymentAmountUsd=round(payment_amount_usd, 2),
            entityType=entity_type,
            paymentMethod=payment_method,
            w9Verified=w9_verified,
            isAttorneyOrLegalServices=is_attorney_or_legal_services,
            complianceVerdict="EXEMPT_CORPORATION",
            federalFilingRequired=False,
            federalThresholdUsd=federal_threshold,
            stateFilingRequired=False,
            stateThresholdUsd=effective_state_threshold,
            directStatePortalRequired=False,
            cfsfCoversNonWithholding=rule.cfsfParticipantForNec,
            filingChannel="None (Corporate Exemption)",
            federalBackupWithholdingRequired=False,
            federalBackupWithholdingUsd=0.0,
            stateBackupWithholdingUsd=0.0,
            stateTaxWithheldUsd=0.0,
            totalBackupWithholdingUsd=0.0,
            maxIrsPenaltyRiskUsd=0.0,
            irsPenaltyTiersUsd={},
            federalDueDate=federal_due_date,
            stateDueDate=state_due_date,
            stateAgencyName=rule.stateAgencyName,
            actionRequired="Keep signed Form W-9 on file confirming corporate status; no 1099-NEC required.",
            ruleExplanation="Payments to C-Corporations, S-Corporations, and tax-exempt nonprofits (non-legal services) are exempt from Form 1099-NEC.",
        )

    # Rule 3: Mandatory 24% Backup Withholding when W-9 / TIN is missing (IRC § 3406)
    backup_withholding_required = (not w9_verified) and (payment_amount_usd > 0.0)
    fed_withholding_usd = (
        round(payment_amount_usd * FEDERAL_BACKUP_WITHHOLDING_RATE, 2)
        if backup_withholding_required
        else 0.0
    )
    state_bw_usd = (
        round(payment_amount_usd * (rule.stateBackupWithholdingPercent / 100.0), 2)
        if backup_withholding_required and rule.stateBackupWithholdingPercent > 0.0
        else 0.0
    )
    total_withholding_usd = round(fed_withholding_usd + state_bw_usd + state_tax_withheld_usd, 2)

    # Federal Form 1099-NEC is required at >= $2,000 (2026) OR from $0.01 if backup withholding applies
    federal_required = backup_withholding_required or (payment_amount_usd >= federal_threshold)

    # State Form 1099-NEC obligation check
    if state_tax_withheld_usd > 0.0 or (backup_withholding_required and rule.hasStateIncomeTax):
        state_required = True
    elif rule.thresholdMode2026 == "NO_STATE_1099_NEC":
        state_required = False
    elif rule.thresholdMode2026 == "FOLLOWS_FEDERAL_THRESHOLD":
        state_required = federal_required
    else:
        state_required = payment_amount_usd >= (effective_state_threshold or 600.0)

    has_any_state_withholding = (state_tax_withheld_usd + state_bw_usd) > 0.0
    direct_state_portal = state_required and (
        not rule.cfsfParticipantForNec
        or (not federal_required)  # IRS CF/SF only transmits if a Federal 1099-NEC is filed!
        or has_any_state_withholding
    )

    if not federal_required and not state_required:
        filing_channel = "None Required"
    elif federal_required and state_required and not direct_state_portal:
        filing_channel = f"IRS FIRE/IRIS + CF/SF Auto-Forward ({rule.stateCode})"
    elif federal_required and direct_state_portal:
        filing_channel = f"IRS FIRE/IRIS + Direct {rule.stateAgencyName}"
    elif federal_required:
        filing_channel = "IRS FIRE/IRIS Only (No State 1099-NEC)"
    else:
        filing_channel = f"Direct {rule.stateAgencyName} Portal ONLY"

    if backup_withholding_required:
        verdict = "CRITICAL_BACKUP_WITHHOLDING_REQUIRED"
        action = (
            f"URGENT: Missing valid W-9/TIN triggers 24% IRS backup withholding (${fed_withholding_usd:,.2f})"
            + (f" plus {rule.stateBackupWithholdingPercent}% {rule.stateCode} withholding (${state_bw_usd:,.2f})" if state_bw_usd > 0 else "")
            + ". Must deposit via EFTPS and file Form 1099-NEC + Form 945 from $0.01!"
        )
    elif (not federal_required) and state_required:
        verdict = "STATE_ONLY_FILING_TRAP"
        action = (
            f"2026 THRESHOLD TRAP: No IRS filing needed (< ${federal_threshold:,.0f}), "
            f"but {rule.stateName} requires DIRECT Form 1099-NEC filing (>= ${effective_state_threshold:,.0f}). "
            f"IRS CF/SF will NOT transmit because no federal form is filed — submit directly to {rule.stateAgencyName} by {state_due_date}."
        )
    elif federal_required and state_required:
        verdict = "FEDERAL_AND_STATE_FILING_REQUIRED"
        action = (
            f"File IRS Form 1099-NEC by {federal_due_date} AND "
            + (f"file directly with {rule.stateAgencyName} by {state_due_date}." if direct_state_portal else f"transmit to {rule.stateName} via IRS CF/SF.")
        )
    elif federal_required:
        verdict = "FEDERAL_ONLY_FILING_REQUIRED"
        action = f"File Federal IRS Form 1099-NEC by {federal_due_date}. No {rule.stateCode} state 1099-NEC required."
    else:
        verdict = "NO_FILING_REQUIRED"
        action = f"Below both ${federal_threshold:,.0f} Federal and {rule.stateCode} thresholds; retain W-9 and ledger records."

    penalty_tiers = dict(IRS_PENALTY_TIERS_USD) if federal_required else {}
    max_penalty = penalty_tiers.get("intentional_disregard", 0.0)

    attorney_note = (
        " Attorney/legal services override corporate exemption."
        if is_attorney_or_legal_services and entity_type in EXEMPT_CORPORATE_ENTITIES
        else ""
    )

    return ComplianceEvaluationRecord(
        contractorOrScenario=scenario_label,
        contractorId=contractor_id,
        taxYear=tax_year,
        stateCode=rule.stateCode,
        stateName=rule.stateName,
        paymentAmountUsd=round(payment_amount_usd, 2),
        entityType=entity_type,
        paymentMethod=payment_method,
        w9Verified=w9_verified,
        isAttorneyOrLegalServices=is_attorney_or_legal_services,
        complianceVerdict=verdict,
        federalFilingRequired=federal_required,
        federalThresholdUsd=federal_threshold,
        stateFilingRequired=state_required,
        stateThresholdUsd=effective_state_threshold,
        directStatePortalRequired=direct_state_portal,
        cfsfCoversNonWithholding=rule.cfsfParticipantForNec,
        filingChannel=filing_channel,
        federalBackupWithholdingRequired=backup_withholding_required,
        federalBackupWithholdingUsd=fed_withholding_usd,
        stateBackupWithholdingUsd=state_bw_usd,
        stateTaxWithheldUsd=round(state_tax_withheld_usd, 2),
        totalBackupWithholdingUsd=total_withholding_usd,
        maxIrsPenaltyRiskUsd=max_penalty,
        irsPenaltyTiersUsd=penalty_tiers,
        federalDueDate=federal_due_date,
        stateDueDate=state_due_date,
        stateAgencyName=rule.stateAgencyName,
        actionRequired=action,
        ruleExplanation=f"{rule.notes}{attorney_note}".strip(),
    )


def build_mcp_summary(
    records: list[ComplianceEvaluationRecord],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Generate a compact, token-efficient MCP compliance executive summary."""
    verdict_counts: dict[str, int] = {}
    for rec in records:
        verdict_counts[rec.complianceVerdict] = verdict_counts.get(rec.complianceVerdict, 0) + 1

    total_bw = round(sum(r.totalBackupWithholdingUsd for r in records), 2)
    total_max_penalty = round(sum(r.maxIrsPenaltyRiskUsd for r in records), 2)
    state_trap_states = sorted({r.stateCode for r in records if r.complianceVerdict == "STATE_ONLY_FILING_TRAP"})
    critical_bw_items = [
        {
            "scenario": r.contractorOrScenario,
            "state": r.stateCode,
            "payment_usd": r.paymentAmountUsd,
            "withholding_due_usd": r.totalBackupWithholdingUsd,
        }
        for r in records
        if r.federalBackupWithholdingRequired
    ]

    return {
        "title": "US 1099-NEC $2,000 Threshold & State Compliance MCP Summary",
        "tax_year": criteria.get("tax_year", 2026),
        "federal_1099_nec_threshold_usd": 2000.0 if criteria.get("tax_year", 2026) >= 2026 else 600.0,
        "criteria": criteria,
        "metrics": {
            "total_evaluations": len(records),
            "verdict_breakdown": verdict_counts,
            "federal_filings_required": sum(1 for r in records if r.federalFilingRequired),
            "state_filings_required": sum(1 for r in records if r.stateFilingRequired),
            "direct_state_portal_uploads_required": sum(1 for r in records if r.directStatePortalRequired),
            "state_only_trap_jurisdictions": state_trap_states,
            "total_backup_withholding_liability_usd": total_bw,
            "total_max_irs_penalty_exposure_usd": total_max_penalty,
        },
        "critical_backup_withholding_alerts": critical_bw_items[:15],
        "compact_results": [
            {
                "scenario": r.contractorOrScenario,
                "state": r.stateCode,
                "amount_usd": r.paymentAmountUsd,
                "verdict": r.complianceVerdict,
                "federal_1099": r.federalFilingRequired,
                "state_1099": r.stateFilingRequired,
                "direct_portal": r.directStatePortalRequired,
                "withholding_usd": r.totalBackupWithholdingUsd,
                "channel": r.filingChannel,
            }
            for r in records[:25]
        ],
    }

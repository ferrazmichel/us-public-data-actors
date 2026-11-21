"""Main entry point for the US 1099-NEC $2,000 Threshold & State Compliance Actor."""

from __future__ import annotations

from typing import Literal

from apify import Actor
from pydantic import BaseModel, Field, field_validator

from .compliance_engine import (
    US_STATES_1099_RULES,
    ComplianceEvaluationRecord,
    EntityType,
    PaymentMethod,
    build_mcp_summary,
    evaluate_1099_compliance,
)


class ContractorBatchItem(BaseModel):
    """Optional contractor item for batch CPA/ERP auditing."""

    contractorId: str | None = Field(default=None)
    name: str | None = Field(default=None)
    state: str = Field(min_length=2, max_length=2)
    paymentAmountUsd: float = Field(ge=0)
    entityType: EntityType = Field(default="individual_sole_prop")
    paymentMethod: PaymentMethod = Field(default="ach_wire_check_cash")
    w9Verified: bool = Field(default=True)
    isAttorneyOrLegalServices: bool = Field(default=False)
    stateTaxWithheldUsd: float = Field(default=0.0, ge=0)

    @field_validator("state", mode="before")
    @classmethod
    def _upper_state(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class ActorInput(BaseModel):
    """Validated Actor input schema."""

    states: list[str] = Field(
        default_factory=lambda: ["CA", "NY", "TX", "PA", "MA", "FL", "IL", "NJ", "OR", "GA"]
    )
    taxYear: int = Field(default=2026, ge=2025, le=2026)
    paymentAmountUsd: float = Field(default=1250.0, ge=0)
    entityType: EntityType = Field(default="individual_sole_prop")
    paymentMethod: PaymentMethod = Field(default="ach_wire_check_cash")
    w9Verified: bool = Field(default=True)
    isAttorneyOrLegalServices: bool = Field(default=False)
    stateTaxWithheldUsd: float = Field(default=0.0, ge=0)
    contractors: list[ContractorBatchItem] = Field(default_factory=list)
    outputMode: Literal["detailed", "mcp_summary"] = Field(default="detailed")

    @field_validator("states", mode="before")
    @classmethod
    def _normalize_states(cls, value: object) -> object:
        if isinstance(value, list):
            return [str(v).strip().upper() for v in value if str(v).strip()]
        return value


async def _safe_charge(event_name: str, count: int = 1) -> None:
    """Charge Pay-Per-Event when running in a monetized Apify environment."""
    if count <= 0:
        return
    try:
        charge_fn = getattr(Actor, "charge", None)
        if callable(charge_fn):
            await charge_fn(event_name=event_name, count=count)
    except Exception as exc:  # noqa: BLE001 - local runs lack PPE configuration
        Actor.log.debug(
            "Skipping PPE charge '%s' (count=%d) in non-monetized context: %s",
            event_name,
            count,
            exc,
        )


async def main() -> None:
    """Run the US 1099-NEC $2,000 Threshold & State Compliance Actor."""
    async with Actor:
        raw_input = await Actor.get_input() or {}
        cfg = ActorInput.model_validate(raw_input)

        records: list[ComplianceEvaluationRecord] = []

        if cfg.contractors:
            Actor.log.info(
                "Auditing batch of %d contractor(s) for taxYear=%d",
                len(cfg.contractors),
                cfg.taxYear,
            )
            for idx, item in enumerate(cfg.contractors, start=1):
                label = item.name or item.contractorId or f"Contractor #{idx}"
                try:
                    records.append(
                        evaluate_1099_compliance(
                            scenario_label=label,
                            contractor_id=item.contractorId,
                            state_code=item.state,
                            tax_year=cfg.taxYear,
                            payment_amount_usd=item.paymentAmountUsd,
                            entity_type=item.entityType,
                            payment_method=item.paymentMethod,
                            w9_verified=item.w9Verified,
                            is_attorney_or_legal_services=item.isAttorneyOrLegalServices,
                            state_tax_withheld_usd=item.stateTaxWithheldUsd,
                        )
                    )
                except ValueError as exc:
                    await Actor.fail(status_message=str(exc))
                    return
        else:
            target_states = (
                sorted(US_STATES_1099_RULES.keys())
                if "ALL" in cfg.states or not cfg.states
                else cfg.states
            )
            Actor.log.info(
                "Evaluating %d US state(s) for taxYear=%d, amount=$%.2f, entity=%s, w9=%s",
                len(target_states),
                cfg.taxYear,
                cfg.paymentAmountUsd,
                cfg.entityType,
                cfg.w9Verified,
            )
            for state_code in target_states:
                try:
                    records.append(
                        evaluate_1099_compliance(
                            scenario_label=f"{state_code} — ${cfg.paymentAmountUsd:,.0f} ({cfg.taxYear})",
                            state_code=state_code,
                            tax_year=cfg.taxYear,
                            payment_amount_usd=cfg.paymentAmountUsd,
                            entity_type=cfg.entityType,
                            payment_method=cfg.paymentMethod,
                            w9_verified=cfg.w9Verified,
                            is_attorney_or_legal_services=cfg.isAttorneyOrLegalServices,
                            state_tax_withheld_usd=cfg.stateTaxWithheldUsd,
                        )
                    )
                except ValueError as exc:
                    await Actor.fail(status_message=str(exc))
                    return

        Actor.log.info("Evaluated %d 1099-NEC compliance record(s).", len(records))

        if cfg.outputMode != "mcp_summary" and records:
            await Actor.push_data([r.model_dump() for r in records])
            await _safe_charge("compliance-check", count=len(records))

        criteria = {
            "tax_year": cfg.taxYear,
            "mode": "contractor_batch" if cfg.contractors else "state_matrix",
            "states": cfg.states if not cfg.contractors else sorted({r.stateCode for r in records}),
            "payment_amount_usd": cfg.paymentAmountUsd,
            "entity_type": cfg.entityType,
            "w9_verified": cfg.w9Verified,
        }
        summary = build_mcp_summary(records, criteria)
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(
            "Saved MCP 1099-NEC Compliance Summary: evaluations=%d, state_traps=%d, withholding_due=$%.2f",
            summary["metrics"]["total_evaluations"],
            len(summary["metrics"]["state_only_trap_jurisdictions"]),
            summary["metrics"]["total_backup_withholding_liability_usd"],
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

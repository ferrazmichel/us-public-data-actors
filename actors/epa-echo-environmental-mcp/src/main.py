"""Main entry point for the EPA ECHO Environmental Compliance Apify Actor."""

from __future__ import annotations

from typing import Literal

from apify import Actor
from pydantic import BaseModel, Field, field_validator

from .echo_client import EpaEchoClient, build_mcp_summary


class ActorInput(BaseModel):
    """Validated Actor input schema."""

    facilityName: str | None = Field(default=None)
    state: str | None = Field(default=None, max_length=2)
    city: str | None = Field(default=None)
    zipCode: str | None = Field(default=None)
    naicsCode: str | None = Field(default=None)
    significantNonComplianceOnly: bool = Field(default=False)
    maxRecords: int = Field(default=50, ge=1, le=200)
    outputMode: Literal["detailed", "mcp_summary"] = Field(default="detailed")

    @field_validator("state", mode="before")
    @classmethod
    def _normalize_state(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip().upper()
            return cleaned or None
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
    """Run the EPA ECHO Environmental Compliance Actor."""
    async with Actor:
        raw_input = await Actor.get_input() or {}
        cfg = ActorInput.model_validate(raw_input)

        if not any([cfg.facilityName, cfg.state, cfg.city, cfg.zipCode, cfg.naicsCode]):
            await Actor.fail(
                status_message=(
                    "At least one search filter must be provided: 'facilityName', "
                    "'state', 'city', 'zipCode', or 'naicsCode'."
                )
            )
            return

        Actor.log.info(
            "Starting EPA ECHO facility search (name=%r, state=%r, city=%r, max=%d, SNC_only=%s)",
            cfg.facilityName,
            cfg.state,
            cfg.city,
            cfg.maxRecords,
            cfg.significantNonComplianceOnly,
        )

        async with EpaEchoClient() as client:
            try:
                facilities = await client.search_facilities(
                    facility_name=cfg.facilityName,
                    state=cfg.state,
                    city=cfg.city,
                    zip_code=cfg.zipCode,
                    naics_code=cfg.naicsCode,
                    significant_non_compliance_only=cfg.significantNonComplianceOnly,
                    max_records=cfg.maxRecords,
                )
            except Exception as exc:
                Actor.log.error("Failed to query EPA ECHO REST Services: %s", exc)
                await Actor.fail(status_message=f"EPA ECHO API Error: {exc}")
                return

        Actor.log.info("EPA ECHO returned %d facility records.", len(facilities))

        # Push detailed facility records to default dataset
        if cfg.outputMode != "mcp_summary" and facilities:
            await Actor.push_data([f.model_dump() for f in facilities])
            # Charge PPE per facility record pushed
            await _safe_charge("facility-record", count=len(facilities))

        # Generate and save MCP Executive Summary
        criteria = {
            "facility_name": cfg.facilityName,
            "state": cfg.state,
            "city": cfg.city,
            "zip_code": cfg.zipCode,
            "naics_code": cfg.naicsCode,
            "significant_non_compliance_only": cfg.significantNonComplianceOnly,
        }
        summary = build_mcp_summary(facilities, criteria)
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(
            "Saved MCP Executive Summary: risk_level=%s, facilities=%d, SNC=%d, penalties=$%.2f",
            summary["risk_level"],
            summary["metrics"]["total_facilities_analyzed"],
            summary["metrics"]["facilities_with_significant_non_compliance"],
            summary["metrics"]["total_penalties_assessed_usd"],
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

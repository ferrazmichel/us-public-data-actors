"""Main entry point for the FMCSA & USDOT Carrier Safety Apify Actor."""

from __future__ import annotations

from typing import Literal

from apify import Actor
from pydantic import BaseModel, Field, field_validator

from .fmcsa_client import FmcsaApiError, FmcsaClient, build_mcp_summary


class ActorInput(BaseModel):
    """Validated Actor input schema."""

    dotNumber: str | None = Field(default=None)
    mcNumber: str | None = Field(default=None)
    carrierName: str | None = Field(default=None)
    state: str | None = Field(default=None, max_length=2)
    city: str | None = Field(default=None)
    statusCode: Literal["A", "I", "ALL"] = Field(default="A")
    addedAfterDate: str | None = Field(default=None)
    minPowerUnits: int = Field(default=0, ge=0)
    hazmatOnly: bool = Field(default=False)
    includeAuthorityAndInsurance: bool = Field(default=True)
    maxRecords: int = Field(default=20, ge=1, le=200)
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
    """Run the FMCSA Carrier Safety & Leads Actor."""
    async with Actor:
        raw_input = await Actor.get_input() or {}
        cfg = ActorInput.model_validate(raw_input)

        if not any(
            [
                cfg.dotNumber,
                cfg.mcNumber,
                cfg.carrierName,
                cfg.state,
                cfg.city,
                cfg.addedAfterDate,
            ]
        ):
            await Actor.fail(
                status_message=(
                    "Provide at least one filter: 'dotNumber', 'mcNumber', "
                    "'carrierName', 'state', 'city', or 'addedAfterDate'."
                )
            )
            return

        Actor.log.info(
            "Querying USDOT/FMCSA (dot=%r, mc=%r, name=%r, state=%r, max=%d, enrich=%s)",
            cfg.dotNumber,
            cfg.mcNumber,
            cfg.carrierName,
            cfg.state,
            cfg.maxRecords,
            cfg.includeAuthorityAndInsurance,
        )

        async with FmcsaClient() as client:
            try:
                carriers = await client.search_carriers(
                    dot_number=cfg.dotNumber,
                    mc_number=cfg.mcNumber,
                    carrier_name=cfg.carrierName,
                    state=cfg.state,
                    city=cfg.city,
                    status_code=cfg.statusCode,
                    added_after_date=cfg.addedAfterDate,
                    min_power_units=cfg.minPowerUnits,
                    hazmat_only=cfg.hazmatOnly,
                    include_authority_and_insurance=cfg.includeAuthorityAndInsurance,
                    max_records=cfg.maxRecords,
                )
            except FmcsaApiError as exc:
                Actor.log.error("FMCSA API error: %s", exc)
                await Actor.fail(status_message=f"FMCSA API Error: {exc}")
                return

        Actor.log.info("FMCSA search returned %d motor carrier profile(s).", len(carriers))

        if cfg.outputMode != "mcp_summary" and carriers:
            await Actor.push_data([c.model_dump() for c in carriers])
            await _safe_charge("carrier-record", count=len(carriers))

        criteria = {
            "dot_number": cfg.dotNumber,
            "mc_number": cfg.mcNumber,
            "carrier_name": cfg.carrierName,
            "state": cfg.state,
            "city": cfg.city,
            "status_code": cfg.statusCode,
            "added_after_date": cfg.addedAfterDate,
            "min_power_units": cfg.minPowerUnits,
            "hazmat_only": cfg.hazmatOnly,
        }
        summary = build_mcp_summary(carriers, criteria)
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(
            "Saved MCP Vetting Summary: overall=%s, carriers=%d, total_trucks=%d",
            summary["overall_vetting_status"],
            summary["metrics"]["total_carriers_analyzed"],
            summary["metrics"]["total_power_units"],
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

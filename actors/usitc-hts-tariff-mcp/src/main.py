"""Main entry point for the USITC HTS Tariff & Landed Cost Calculator Apify Actor."""

from __future__ import annotations

from typing import Literal

from apify import Actor
from pydantic import BaseModel, Field, field_validator

from .hts_client import HtsApiError, HtsClient, build_mcp_summary


class ActorInput(BaseModel):
    """Validated Actor input schema."""

    query: str = Field(min_length=1)
    countryOfOrigin: str = Field(default="CN", min_length=2, max_length=2)
    compareCountries: list[str] = Field(default_factory=lambda: ["CN", "VN", "MX", "KR"])
    shipmentValueUsd: float = Field(default=25000.0, gt=0)
    freightAndInsuranceUsd: float = Field(default=1200.0, ge=0)
    transportMode: Literal["ocean", "air", "truck"] = Field(default="ocean")
    additionalTariffPercent: float | None = Field(default=None, ge=0, le=500)
    includeChapter99Notes: bool = Field(default=True)
    maxResults: int = Field(default=10, ge=1, le=100)
    outputMode: Literal["detailed", "mcp_summary"] = Field(default="detailed")

    @field_validator("countryOfOrigin", mode="before")
    @classmethod
    def _normalize_origin(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip().upper()
            return cleaned or "CN"
        return value

    @field_validator("compareCountries", mode="before")
    @classmethod
    def _normalize_compare(cls, value: object) -> object:
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
    """Run the USITC HTS Tariff & Landed Cost Calculator Actor."""
    async with Actor:
        raw_input = await Actor.get_input() or {}
        cfg = ActorInput.model_validate(raw_input)

        Actor.log.info(
            "Querying USITC HTS (query=%r, origin=%s, value=$%.2f, mode=%s, max=%d)",
            cfg.query,
            cfg.countryOfOrigin,
            cfg.shipmentValueUsd,
            cfg.transportMode,
            cfg.maxResults,
        )

        async with HtsClient() as client:
            try:
                records = await client.search_and_calculate(
                    query=cfg.query,
                    country_of_origin=cfg.countryOfOrigin,
                    compare_countries=cfg.compareCountries,
                    shipment_value_usd=cfg.shipmentValueUsd,
                    freight_and_insurance_usd=cfg.freightAndInsuranceUsd,
                    transport_mode=cfg.transportMode,
                    additional_tariff_percent=cfg.additionalTariffPercent,
                    include_chapter99_notes=cfg.includeChapter99Notes,
                    max_results=cfg.maxResults,
                )
            except HtsApiError as exc:
                Actor.log.error("USITC HTS API error: %s", exc)
                await Actor.fail(status_message=f"USITC HTS API Error: {exc}")
                return

        Actor.log.info("USITC HTS search returned %d calculated tariff item(s).", len(records))

        if cfg.outputMode != "mcp_summary" and records:
            await Actor.push_data([r.model_dump() for r in records])
            await _safe_charge("hts-tariff-record", count=len(records))

        criteria = {
            "query": cfg.query,
            "country_of_origin": cfg.countryOfOrigin,
            "compare_countries": cfg.compareCountries,
            "shipment_value_usd": cfg.shipmentValueUsd,
            "freight_and_insurance_usd": cfg.freightAndInsuranceUsd,
            "transport_mode": cfg.transportMode,
            "additional_tariff_override": cfg.additionalTariffPercent,
        }
        summary = build_mcp_summary(records, criteria)
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(
            "Saved MCP Tariff Summary: status=%s, lines=%d",
            summary["status"],
            len(records),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

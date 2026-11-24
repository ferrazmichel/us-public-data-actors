"""Main entry point for the USAspending Federal Contracts & Re-Compete Radar Apify Actor."""

from __future__ import annotations

from typing import Literal

from apify import Actor
from pydantic import BaseModel, Field, field_validator

from .usaspending_client import (
    UsaSpendingApiError,
    UsaSpendingClient,
    build_mcp_summary,
)


class ActorInput(BaseModel):
    """Validated Actor input schema."""

    keywords: list[str] = Field(default_factory=lambda: ["cybersecurity"])
    recipientNames: list[str] = Field(default_factory=list)
    naicsCodes: list[str] = Field(default_factory=list)
    awardingAgency: str | None = Field(default=None)
    placeOfPerformanceState: str | None = Field(default=None)
    awardType: Literal["contracts", "grants", "all"] = Field(default="contracts")
    minAwardAmountUsd: float | None = Field(default=None, ge=0)
    startDateFrom: str | None = Field(default="2024-01-01")
    endDateTo: str | None = Field(default="2027-12-31")
    expiringWithinDays: int | None = Field(default=None, ge=1, le=1095)
    maxRecords: int = Field(default=25, ge=1, le=200)
    outputMode: Literal["detailed", "mcp_summary"] = Field(default="detailed")

    @field_validator("keywords", "recipientNames", "naicsCodes", mode="before")
    @classmethod
    def _clean_string_list(cls, value: object) -> object:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return value

    @field_validator("placeOfPerformanceState", mode="before")
    @classmethod
    def _normalize_state(cls, value: object) -> object:
        if isinstance(value, str):
            clean = value.strip().upper()
            return clean or None
        return value


async def main() -> None:
    """Run the USAspending Federal Contracts & Re-Compete Radar Actor."""
    async with Actor:
        raw_input = await Actor.get_input() or {}
        cfg = ActorInput.model_validate(raw_input)

        Actor.log.info(
            "Querying USAspending.gov (keywords=%r, naics=%r, agency=%r, state=%r, expiring_days=%r, max=%d)",
            cfg.keywords,
            cfg.naicsCodes,
            cfg.awardingAgency,
            cfg.placeOfPerformanceState,
            cfg.expiringWithinDays,
            cfg.maxRecords,
        )

        async with UsaSpendingClient() as client:
            try:
                records = await client.search_awards(
                    keywords=cfg.keywords,
                    recipient_names=cfg.recipientNames,
                    naics_codes=cfg.naicsCodes,
                    awarding_agency=cfg.awardingAgency,
                    place_of_performance_state=cfg.placeOfPerformanceState,
                    award_type=cfg.awardType,
                    min_award_amount_usd=cfg.minAwardAmountUsd,
                    start_date_from=cfg.startDateFrom,
                    end_date_to=cfg.endDateTo,
                    expiring_within_days=cfg.expiringWithinDays,
                    max_records=cfg.maxRecords,
                )
            except UsaSpendingApiError as exc:
                Actor.log.error("USAspending API error: %s", exc)
                await Actor.fail(status_message=f"USAspending API Error: {exc}")
                return

        Actor.log.info("USAspending returned %d federal award record(s).", len(records))

        if cfg.outputMode != "mcp_summary" and records:
            # Apify automatically charges the synthetic 'apify-default-dataset-item' PPE event on push_data.
            await Actor.push_data([r.model_dump() for r in records])

        criteria = {
            "keywords": cfg.keywords,
            "recipient_names": cfg.recipientNames,
            "naics_codes": cfg.naicsCodes,
            "awarding_agency": cfg.awardingAgency,
            "place_of_performance_state": cfg.placeOfPerformanceState,
            "award_type": cfg.awardType,
            "expiring_within_days": cfg.expiringWithinDays,
        }
        summary = build_mcp_summary(records, criteria)
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(
            "Saved MCP USAspending Summary: status=%s, awards=%d, urgent_recompete=%d",
            summary["status"],
            summary["metrics"]["total_awards_returned"],
            summary["metrics"]["urgent_recompete_count"],
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

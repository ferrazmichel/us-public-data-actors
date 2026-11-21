"""Main entry point for the openFDA Drug, Device & Food Recall Radar Actor."""

from __future__ import annotations

from typing import Literal

from apify import Actor
from pydantic import BaseModel, Field, field_validator

from .openfda_client import (
    DomainChoice,
    OpenFdaApiError,
    OpenFdaClient,
    build_mcp_summary,
)


class ActorInput(BaseModel):
    """Validated Actor input schema."""

    domain: DomainChoice = Field(default="all")
    searchQuery: str | None = Field(default=None)
    recallingFirm: str | None = Field(default=None)
    classification: Literal["ALL", "Class I", "Class II", "Class III"] = Field(default="Class I")
    status: Literal["Ongoing", "Terminated", "Completed", "ALL"] = Field(default="Ongoing")
    state: str | None = Field(default=None, max_length=2)
    reportDateFrom: str | None = Field(default=None)
    maxRecords: int = Field(default=15, ge=1, le=200)
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
    """Run the openFDA Drug, Device & Food Recall Radar Actor."""
    async with Actor:
        raw_input = await Actor.get_input() or {}
        cfg = ActorInput.model_validate(raw_input)

        Actor.log.info(
            "Querying openFDA Enforcement APIs (domain=%s, class=%s, status=%s, firm=%r, query=%r, max=%d)",
            cfg.domain,
            cfg.classification,
            cfg.status,
            cfg.recallingFirm,
            cfg.searchQuery,
            cfg.maxRecords,
        )

        async with OpenFdaClient() as client:
            try:
                recalls = await client.search_recalls(
                    domain=cfg.domain,
                    search_query=cfg.searchQuery,
                    recalling_firm=cfg.recallingFirm,
                    classification=cfg.classification,
                    status=cfg.status,
                    state=cfg.state,
                    report_date_from=cfg.reportDateFrom,
                    max_records=cfg.maxRecords,
                )
            except OpenFdaApiError as exc:
                Actor.log.error("openFDA API error: %s", exc)
                await Actor.fail(status_message=f"openFDA API Error: {exc}")
                return

        Actor.log.info("openFDA search returned %d normalized recall record(s).", len(recalls))

        if cfg.outputMode != "mcp_summary" and recalls:
            await Actor.push_data([r.model_dump() for r in recalls])
            await _safe_charge("fda-recall-record", count=len(recalls))

        criteria = {
            "domain": cfg.domain,
            "search_query": cfg.searchQuery,
            "recalling_firm": cfg.recallingFirm,
            "classification": cfg.classification,
            "status": cfg.status,
            "state": cfg.state,
            "report_date_from": cfg.reportDateFrom,
        }
        summary = build_mcp_summary(recalls, criteria)
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(
            "Saved MCP Recall Radar Summary: overall=%s, total=%d, critical=%d",
            summary["overall_alert_level"],
            summary["metrics"]["total_recalls"],
            summary["metrics"].get("risk_breakdown", {}).get("CRITICAL", 0),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

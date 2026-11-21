"""Main entry point for the SEC EDGAR Filings & XBRL Financials Apify Actor."""

from __future__ import annotations

from typing import Literal

from apify import Actor
from pydantic import BaseModel, Field, field_validator

from .sec_client import SecEdgarApiError, SecEdgarClient, build_mcp_summary


class ActorInput(BaseModel):
    """Validated Actor input schema."""

    tickersOrCiks: list[str] = Field(default_factory=lambda: ["AAPL", "NVDA", "MSFT"])
    companyName: str | None = Field(default=None)
    forms: list[str] = Field(default_factory=lambda: ["10-K", "10-Q", "8-K"])
    filingDateFrom: str | None = Field(default=None)
    includeFinancialSnapshot: bool = Field(default=True)
    maxFilingsPerCompany: int = Field(default=5, ge=1, le=100)
    outputMode: Literal["detailed", "mcp_summary"] = Field(default="detailed")

    @field_validator("tickersOrCiks", "forms", mode="before")
    @classmethod
    def _normalize_list(cls, value: object) -> object:
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
    """Run the SEC EDGAR Filings & XBRL Financials Actor."""
    async with Actor:
        raw_input = await Actor.get_input() or {}
        cfg = ActorInput.model_validate(raw_input)

        if not cfg.tickersOrCiks and not (cfg.companyName and cfg.companyName.strip()):
            await Actor.fail(
                status_message="Provide at least one stock ticker/CIK in 'tickersOrCiks' or set 'companyName'."
            )
            return

        Actor.log.info(
            "Querying SEC EDGAR (tickers=%r, name=%r, forms=%r, snapshot=%s, max=%d)",
            cfg.tickersOrCiks,
            cfg.companyName,
            cfg.forms,
            cfg.includeFinancialSnapshot,
            cfg.maxFilingsPerCompany,
        )

        async with SecEdgarClient() as client:
            try:
                records, snapshots = await client.search_filings(
                    tickers_or_ciks=cfg.tickersOrCiks,
                    company_name=cfg.companyName,
                    forms=cfg.forms,
                    filing_date_from=cfg.filingDateFrom,
                    include_financial_snapshot=cfg.includeFinancialSnapshot,
                    max_filings_per_company=cfg.maxFilingsPerCompany,
                )
            except SecEdgarApiError as exc:
                Actor.log.error("SEC EDGAR API error: %s", exc)
                await Actor.fail(status_message=f"SEC EDGAR API Error: {exc}")
                return

        Actor.log.info(
            "SEC EDGAR returned %d filing record(s) across %d company snapshot(s).",
            len(records),
            len(snapshots),
        )

        if cfg.outputMode != "mcp_summary" and records:
            await Actor.push_data([r.model_dump() for r in records])
            await _safe_charge("sec-filing-record", count=len(records))

        criteria = {
            "tickers_or_ciks": cfg.tickersOrCiks,
            "company_name": cfg.companyName,
            "forms": cfg.forms,
            "filing_date_from": cfg.filingDateFrom,
            "include_financial_snapshot": cfg.includeFinancialSnapshot,
        }
        summary = build_mcp_summary(records, snapshots, criteria)
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(
            "Saved MCP SEC Summary: status=%s, filings=%d",
            summary["status"],
            summary["metrics"]["total_filings_returned"],
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

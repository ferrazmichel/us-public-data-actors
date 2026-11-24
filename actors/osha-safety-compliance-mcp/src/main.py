"""Main entry point for the OSHA Safety & Compliance Apify Actor."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from apify import Actor
from pydantic import BaseModel, Field, field_validator

from .dol_client import DolApiError, DolOshaClient, build_mcp_summary

_PLACEHOLDER_ENV_VALUES = frozenset({"replace_with_your_free_dol_api_key"})


def _load_local_env(env_path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a local .env file without overriding existing env vars."""
    path = env_path or (Path(__file__).resolve().parent.parent / ".env")
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value in _PLACEHOLDER_ENV_VALUES:
            continue
        os.environ.setdefault(key, value)


class ActorInput(BaseModel):
    """Validated Actor input schema."""

    establishmentName: str | None = Field(default=None)
    state: str | None = Field(default=None, max_length=2)
    naicsCode: str | None = Field(default=None)
    openDateFrom: str | None = Field(default=None)
    openDateTo: str | None = Field(default=None)
    includeViolations: bool = Field(default=True)
    maxRecords: int = Field(default=50, ge=1, le=1000)
    outputMode: Literal["detailed", "mcp_summary"] = Field(default="detailed")
    dolApiKey: str | None = Field(default=None)

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
            "Skipping PPE charge '%s' (count=%d) in non-monetized/local context: %s",
            event_name,
            count,
            exc,
        )


async def main() -> None:
    """Run the OSHA Safety & Compliance Actor."""
    _load_local_env()
    async with Actor:
        raw_input = await Actor.get_input() or {}
        cfg = ActorInput.model_validate(raw_input)

        api_key = (cfg.dolApiKey or os.getenv("DOL_API_KEY") or "").strip()
        if not api_key:
            await Actor.fail(
                status_message=(
                    "Missing DOL API Key. Provide 'dolApiKey' in input or set the "
                    "DOL_API_KEY environment variable on the Actor."
                )
            )
            return

        if not any(
            [
                cfg.establishmentName,
                cfg.state,
                cfg.naicsCode,
                cfg.openDateFrom,
                cfg.openDateTo,
            ]
        ):
            Actor.log.warning(
                "No search filters provided; falling back to default sample query "
                "(establishmentName='Amazon', state='TX', maxRecords<=10)."
            )
            cfg.establishmentName = "Amazon"
            cfg.state = "TX"
            cfg.maxRecords = min(cfg.maxRecords, 10)

        Actor.log.info(
            "Querying DOL OSHA inspections (name=%r, state=%r, naics=%r, max=%d)",
            cfg.establishmentName,
            cfg.state,
            cfg.naicsCode,
            cfg.maxRecords,
        )

        async with DolOshaClient(api_key=api_key) as client:
            try:
                inspections = await client.fetch_inspections(
                    establishment_name=cfg.establishmentName,
                    state=cfg.state,
                    naics_code=cfg.naicsCode,
                    open_date_from=cfg.openDateFrom,
                    open_date_to=cfg.openDateTo,
                    max_records=cfg.maxRecords,
                )

                if cfg.includeViolations and inspections:
                    Actor.log.info(
                        "Enriching %d inspections with OSHA violations...",
                        len(inspections),
                    )
                    inspections = await client.enrich_inspections_with_violations(
                        inspections
                    )
            except DolApiError as exc:
                await Actor.fail(status_message=str(exc))
                return

        if inspections:
            await Actor.push_data(inspections)
            await _safe_charge("inspection-record", count=len(inspections))

        summary = build_mcp_summary(
            inspections,
            query_params={
                "establishmentName": cfg.establishmentName,
                "state": cfg.state,
                "naicsCode": cfg.naicsCode,
                "openDateFrom": cfg.openDateFrom,
                "openDateTo": cfg.openDateTo,
                "includeViolations": cfg.includeViolations,
            },
        )
        await Actor.set_value("OUTPUT", summary)

        if cfg.outputMode == "mcp_summary":
            await _safe_charge("mcp-summary", count=1)

        Actor.log.info(
            "Done. Returned %d inspections (%d violations, $%.2f current penalties).",
            summary["metrics"]["inspections_returned"],
            summary["metrics"]["total_violations"],
            summary["metrics"]["total_current_penalty_usd"],
        )

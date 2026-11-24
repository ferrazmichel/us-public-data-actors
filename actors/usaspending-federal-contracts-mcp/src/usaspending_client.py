"""Official USAspending.gov API v2 client and Re-Compete Radar enrichment."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

import certifi
import httpx
from pydantic import BaseModel

USASPENDING_AWARD_SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

AWARD_TYPE_MAP: dict[str, list[str]] = {
    "contracts": ["A", "B", "C", "D"],
    "grants": ["02", "03", "04", "05"],
    "all": ["A", "B", "C", "D", "02", "03", "04", "05"],
}

SEARCH_FIELDS: list[str] = [
    "Award ID",
    "Recipient Name",
    "Start Date",
    "End Date",
    "Award Amount",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Description",
    "Place of Performance State Code",
    "generated_internal_id",
]


class UsaSpendingApiError(RuntimeError):
    """Raised when USAspending.gov API returns an error or invalid payload."""


class FederalAwardRecord(BaseModel):
    """Normalized US federal contract or grant award with Re-Compete Radar metadata."""

    awardId: str
    recipientName: str
    awardAmountUsd: float
    awardingAgency: str
    awardingSubAgency: str | None = None
    placeOfPerformanceState: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    daysUntilExpiration: int | None = None
    recompetePriority: str = "UNKNOWN"
    description: str = ""
    awardUrl: str | None = None


def classify_recompete(
    end_date_str: str | None,
    reference_date: date | None = None,
) -> tuple[int | None, str]:
    """Compute days until expiration and classify Re-Compete Radar priority."""
    if not end_date_str:
        return None, "UNKNOWN"
    try:
        end_dt = date.fromisoformat(str(end_date_str).strip()[:10])
    except ValueError:
        return None, "UNKNOWN"

    ref = reference_date or datetime.now(timezone.utc).date()
    delta = (end_dt - ref).days
    if delta < 0:
        return delta, "EXPIRED"
    if delta <= 180:
        return delta, "URGENT_RECOMPETE"
    if delta <= 365:
        return delta, "UPCOMING_RECOMPETE"
    return delta, "ACTIVE_LONG_TERM"


def build_search_payload(
    *,
    keywords: list[str] | None = None,
    recipient_names: list[str] | None = None,
    naics_codes: list[str] | None = None,
    awarding_agency: str | None = None,
    place_of_performance_state: str | None = None,
    award_type: str = "contracts",
    min_award_amount_usd: float | None = None,
    start_date_from: str | None = "2024-01-01",
    end_date_to: str | None = "2027-12-31",
    limit: int = 25,
    page: int = 1,
) -> dict[str, Any]:
    """Build official USAspending /v2/search/spending_by_award/ request JSON."""
    filters: dict[str, Any] = {
        "award_type_codes": AWARD_TYPE_MAP.get(award_type, AWARD_TYPE_MAP["contracts"]),
    }

    if start_date_from or end_date_to:
        filters["time_period"] = [
            {
                "start_date": (start_date_from or "2020-01-01").strip(),
                "end_date": (end_date_to or "2027-12-31").strip(),
            }
        ]

    clean_keywords = [k.strip() for k in (keywords or []) if k and k.strip()]
    if clean_keywords:
        filters["keywords"] = clean_keywords

    clean_recipients = [r.strip() for r in (recipient_names or []) if r and r.strip()]
    if clean_recipients:
        filters["recipient_search_text"] = clean_recipients

    clean_naics = [n.strip() for n in (naics_codes or []) if n and n.strip()]
    if clean_naics:
        filters["naics_codes"] = {"require": clean_naics}

    if awarding_agency and awarding_agency.strip():
        filters["agencies"] = [
            {
                "type": "awarding",
                "tier": "toptier",
                "name": awarding_agency.strip(),
            }
        ]

    if place_of_performance_state and place_of_performance_state.strip():
        filters["place_of_performance_locations"] = [
            {
                "country": "USA",
                "state": place_of_performance_state.strip().upper(),
            }
        ]

    if min_award_amount_usd is not None and min_award_amount_usd > 0:
        filters["award_amounts"] = [{"lower_bound": float(min_award_amount_usd)}]

    return {
        "fields": SEARCH_FIELDS,
        "filters": filters,
        "limit": max(1, min(int(limit), 100)),
        "page": max(1, int(page)),
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }


def _normalize_award(raw: dict[str, Any], reference_date: date | None = None) -> FederalAwardRecord:
    """Convert raw USAspending result row into a FederalAwardRecord."""
    award_id = str(raw.get("Award ID") or raw.get("internal_id") or "").strip() or "UNKNOWN"
    recipient = str(raw.get("Recipient Name") or "").strip() or "UNKNOWN"
    amount_raw = raw.get("Award Amount")
    try:
        amount_usd = round(float(amount_raw), 2) if amount_raw is not None else 0.0
    except (TypeError, ValueError):
        amount_usd = 0.0

    end_date = raw.get("End Date")
    days_left, priority = classify_recompete(end_date, reference_date=reference_date)
    internal_id = str(raw.get("generated_internal_id") or "").strip()
    award_url = f"https://www.usaspending.gov/award/{internal_id}" if internal_id else None

    return FederalAwardRecord(
        awardId=award_id,
        recipientName=recipient,
        awardAmountUsd=amount_usd,
        awardingAgency=str(raw.get("Awarding Agency") or "").strip() or "UNKNOWN",
        awardingSubAgency=str(raw.get("Awarding Sub Agency") or "").strip() or None,
        placeOfPerformanceState=str(raw.get("Place of Performance State Code") or "").strip() or None,
        startDate=str(raw.get("Start Date") or "").strip() or None,
        endDate=str(end_date).strip() if end_date else None,
        daysUntilExpiration=days_left,
        recompetePriority=priority,
        description=str(raw.get("Description") or "").strip(),
        awardUrl=award_url,
    )


class UsaSpendingClient:
    """Async client for USAspending.gov v2 award search endpoint."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> UsaSpendingClient:
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            verify=certifi.where(),
            transport=self._transport,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "USAspendingMcpActor/0.1",
            },
        )
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _post_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            raise UsaSpendingApiError("Client must be used within an 'async with' context.")

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.post(USASPENDING_AWARD_SEARCH_URL, json=payload)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise UsaSpendingApiError(f"Network error contacting USAspending API: {exc}") from exc

            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self._max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue

            if resp.status_code >= 400:
                detail = resp.text[:300]
                raise UsaSpendingApiError(f"HTTP {resp.status_code} from USAspending API: {detail}")

            try:
                data = resp.json()
            except ValueError as exc:
                raise UsaSpendingApiError(f"Invalid JSON returned by USAspending API: {exc}") from exc

            if not isinstance(data, dict) or "results" not in data:
                raise UsaSpendingApiError("Unexpected response shape from USAspending API.")
            return data

        raise UsaSpendingApiError(f"USAspending API failed after retries: {last_exc}")

    async def search_awards(
        self,
        *,
        keywords: list[str] | None = None,
        recipient_names: list[str] | None = None,
        naics_codes: list[str] | None = None,
        awarding_agency: str | None = None,
        place_of_performance_state: str | None = None,
        award_type: str = "contracts",
        min_award_amount_usd: float | None = None,
        start_date_from: str | None = "2024-01-01",
        end_date_to: str | None = "2027-12-31",
        expiring_within_days: int | None = None,
        max_records: int = 25,
        reference_date: date | None = None,
    ) -> list[FederalAwardRecord]:
        """Fetch, paginate, and enrich federal awards with Re-Compete Radar fields."""
        fetch_target = min(max_records * 4, 200) if expiring_within_days is not None else max_records
        collected: list[FederalAwardRecord] = []
        page = 1

        while len(collected) < fetch_target:
            page_limit = min(100, fetch_target - len(collected))
            payload = build_search_payload(
                keywords=keywords,
                recipient_names=recipient_names,
                naics_codes=naics_codes,
                awarding_agency=awarding_agency,
                place_of_performance_state=place_of_performance_state,
                award_type=award_type,
                min_award_amount_usd=min_award_amount_usd,
                start_date_from=start_date_from,
                end_date_to=end_date_to,
                limit=page_limit,
                page=page,
            )
            data = await self._post_search(payload)
            rows = data.get("results") or []
            if not rows:
                break

            for row in rows:
                if isinstance(row, dict):
                    collected.append(_normalize_award(row, reference_date=reference_date))

            page_meta = data.get("page_metadata") or {}
            if not page_meta.get("hasNext"):
                break
            page += 1

        if expiring_within_days is not None:
            filtered = [
                r
                for r in collected
                if r.daysUntilExpiration is not None and 0 <= r.daysUntilExpiration <= expiring_within_days
            ]
            filtered.sort(key=lambda r: (r.daysUntilExpiration or 99999, -r.awardAmountUsd))
            return filtered[:max_records]

        return collected[:max_records]


def build_mcp_summary(
    records: list[FederalAwardRecord],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Build compact <2KB MCP executive GovCon and Re-Compete summary."""
    total_count = len(records)
    total_value = round(sum(r.awardAmountUsd for r in records), 2)
    avg_value = round(total_value / total_count, 2) if total_count else 0.0

    recompete_counts = Counter(r.recompetePriority for r in records)
    incumbent_totals: Counter[str] = Counter()
    agency_counts = Counter(r.awardingAgency for r in records)

    for rec in records:
        incumbent_totals[rec.recipientName] += rec.awardAmountUsd

    top_incumbents = [
        {"recipient": name, "total_award_usd": round(val, 2)}
        for name, val in incumbent_totals.most_common(5)
    ]
    top_agencies = [{"agency": name, "count": cnt} for name, cnt in agency_counts.most_common(5)]

    digest = [
        {
            "award_id": r.awardId,
            "recipient": r.recipientName[:60],
            "amount_usd": r.awardAmountUsd,
            "agency": r.awardingAgency,
            "state": r.placeOfPerformanceState,
            "end_date": r.endDate,
            "days_left": r.daysUntilExpiration,
            "recompete": r.recompetePriority,
            "url": r.awardUrl,
        }
        for r in records[:10]
    ]

    return {
        "title": "USAspending Federal Contracts & Re-Compete Radar MCP Summary",
        "status": "OK" if total_count > 0 else "NO_MATCHES",
        "criteria": criteria,
        "metrics": {
            "total_awards_returned": total_count,
            "total_award_value_usd": total_value,
            "avg_award_value_usd": avg_value,
            "urgent_recompete_count": recompete_counts.get("URGENT_RECOMPETE", 0),
            "upcoming_recompete_count": recompete_counts.get("UPCOMING_RECOMPETE", 0),
            "recompete_breakdown": dict(recompete_counts),
            "top_incumbents": top_incumbents,
            "top_agencies": top_agencies,
        },
        "top_awards_digest": digest,
    }

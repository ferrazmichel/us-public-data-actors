"""Async client for the US Department of Labor (DOL) Open Data OSHA API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import Counter
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# DOL Open Data caps individual GET calls at 200 records per page.
DOL_MAX_PAGE_SIZE = 200
DEFAULT_DOL_BASE_URL = "https://data.dol.gov/get"
DEFAULT_INSPECTION_PATH = "osha/inspection"
DEFAULT_VIOLATION_PATH = "osha/violation"


class DolApiError(RuntimeError):
    """Raised when the DOL Open Data API returns a non-recoverable error."""


def _safe_float(value: Any) -> float:
    """Convert numeric or currency-like string values to float safely."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    """Normalize common DOL Open Data JSON envelope shapes into a list of dicts."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return [item for item in payload["data"] if isinstance(item, dict)]
        d_obj = payload.get("d")
        if isinstance(d_obj, dict) and isinstance(d_obj.get("results"), list):
            return [item for item in d_obj["results"] if isinstance(item, dict)]
        if isinstance(d_obj, list):
            return [item for item in d_obj if isinstance(item, dict)]
    return []


def build_inspection_filters(
    *,
    establishment_name: str | None = None,
    state: str | None = None,
    naics_code: str | None = None,
    open_date_from: str | None = None,
    open_date_to: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Build DOL `filter_object` structure for OSHA inspection queries.

    Note: Verify the exact operator syntax supported by the active DOL API
    version (`eq`, `like`, `gt`, `lt` vs. object map) during the first live test.
    """
    conditions: list[dict[str, Any]] = []

    if establishment_name:
        conditions.append(
            {
                "field": "estab_name",
                "operator": "like",
                "value": f"%{establishment_name.strip()}%",
            }
        )
    if state:
        conditions.append(
            {"field": "site_state", "operator": "eq", "value": state.strip().upper()}
        )
    if naics_code:
        conditions.append(
            {"field": "naics_code", "operator": "like", "value": f"{naics_code.strip()}%"}
        )
    if open_date_from:
        conditions.append(
            {"field": "open_date", "operator": "gt", "value": open_date_from.strip()}
        )
    if open_date_to:
        conditions.append(
            {"field": "open_date", "operator": "lt", "value": open_date_to.strip()}
        )

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"and": conditions}


class DolOshaClient:
    """Asynchronous client handling pagination, retries, and violation joins."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        inspection_path: str | None = None,
        violation_path: str | None = None,
        timeout_seconds: float = 25.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("A non-empty DOL API key is required.")

        self.api_key = api_key.strip()
        self.base_url = (
            base_url or os.getenv("DOL_API_BASE_URL") or DEFAULT_DOL_BASE_URL
        ).rstrip("/")
        self.inspection_path = (
            inspection_path
            or os.getenv("DOL_OSHA_INSPECTION_PATH")
            or DEFAULT_INSPECTION_PATH
        ).lstrip("/")
        self.violation_path = (
            violation_path
            or os.getenv("DOL_OSHA_VIOLATION_PATH")
            or DEFAULT_VIOLATION_PATH
        ).lstrip("/")
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "X-API-KEY": self.api_key,
                "Accept": "application/json",
            },
        )

    async def __aenter__(self) -> DolOshaClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def _get_page(
        self,
        resource_path: str,
        *,
        limit: int,
        offset: int,
        filter_object: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a single paginated GET call with exponential backoff."""
        url = f"{self.base_url}/{resource_path.lstrip('/')}"
        params: dict[str, Any] = {
            "limit": min(limit, DOL_MAX_PAGE_SIZE),
            "offset": offset,
        }
        if filter_object is not None:
            params["filter_object"] = json.dumps(filter_object)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = await self._client.get(url, params=params)
                if response.status_code in (429, 500, 502, 503, 504):
                    delay = 1.5 * (2**attempt)
                    logger.warning(
                        "DOL API transient HTTP %s on %s (attempt %d/%d); retrying in %.1fs",
                        response.status_code,
                        url,
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.status_code >= 400:
                    snippet = response.text[:400].replace("\n", " ")
                    raise DolApiError(
                        f"DOL API error HTTP {response.status_code} at {url}: {snippet}"
                    )

                return _extract_records(response.json())
            except httpx.RequestError as exc:
                last_error = exc
                delay = 1.5 * (2**attempt)
                logger.warning(
                    "Network error calling DOL API (%s); retrying in %.1fs",
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise DolApiError(
            f"DOL API failed after {self.max_retries} attempts at {url}: {last_error}"
        )

    async def fetch_inspections(
        self,
        *,
        establishment_name: str | None = None,
        state: str | None = None,
        naics_code: str | None = None,
        open_date_from: str | None = None,
        open_date_to: str | None = None,
        max_records: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch OSHA inspections across paginated DOL API calls."""
        filter_obj = build_inspection_filters(
            establishment_name=establishment_name,
            state=state,
            naics_code=naics_code,
            open_date_from=open_date_from,
            open_date_to=open_date_to,
        )

        results: list[dict[str, Any]] = []
        offset = 0
        while len(results) < max_records:
            page_limit = min(DOL_MAX_PAGE_SIZE, max_records - len(results))
            batch = await self._get_page(
                self.inspection_path,
                limit=page_limit,
                offset=offset,
                filter_object=filter_obj,
            )
            if not batch:
                break
            results.extend(batch)
            if len(batch) < page_limit:
                break
            offset += len(batch)

        return results[:max_records]

    async def fetch_violations_for_activity(
        self, activity_nr: str, *, max_violations: int = 200
    ) -> list[dict[str, Any]]:
        """Fetch all OSHA violations associated with a single inspection activity_nr."""
        if not activity_nr:
            return []
        filter_obj = {"field": "activity_nr", "operator": "eq", "value": str(activity_nr)}
        return await self._get_page(
            self.violation_path,
            limit=min(max_violations, DOL_MAX_PAGE_SIZE),
            offset=0,
            filter_object=filter_obj,
        )

    async def enrich_inspections_with_violations(
        self,
        inspections: list[dict[str, Any]],
        *,
        concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """Attach normalized violation summaries and penalty totals to inspections."""
        semaphore = asyncio.Semaphore(concurrency)

        async def _enrich_one(record: dict[str, Any]) -> dict[str, Any]:
            enriched = dict(record)
            activity_nr = str(record.get("activity_nr") or "").strip()
            if not activity_nr:
                enriched["violations"] = []
                enriched["violation_count"] = 0
                enriched["total_initial_penalty"] = 0.0
                enriched["total_current_penalty"] = 0.0
                return enriched

            async with semaphore:
                violations = await self.fetch_violations_for_activity(activity_nr)

            total_initial = sum(
                _safe_float(v.get("initial_penalty")) for v in violations
            )
            total_current = sum(
                _safe_float(v.get("current_penalty")) for v in violations
            )

            enriched["violations"] = violations
            enriched["violation_count"] = len(violations)
            enriched["total_initial_penalty"] = round(total_initial, 2)
            enriched["total_current_penalty"] = round(total_current, 2)
            return enriched

        return await asyncio.gather(*(_enrich_one(item) for item in inspections))


def build_mcp_summary(
    inspections: list[dict[str, Any]],
    *,
    query_params: dict[str, Any],
) -> dict[str, Any]:
    """Produce a compact, token-efficient compliance digest for AI agents (MCP)."""
    total_violations = 0
    total_initial_penalty = 0.0
    total_current_penalty = 0.0
    violation_types: Counter[str] = Counter()
    cited_standards: Counter[str] = Counter()
    states_seen: Counter[str] = Counter()
    compact_inspections: list[dict[str, Any]] = []

    for item in inspections:
        state_code = str(item.get("site_state") or "").strip()
        if state_code:
            states_seen[state_code] += 1

        violations = item.get("violations") or []
        v_count = int(item.get("violation_count") or len(violations))
        init_pen = _safe_float(item.get("total_initial_penalty"))
        curr_pen = _safe_float(item.get("total_current_penalty"))

        total_violations += v_count
        total_initial_penalty += init_pen
        total_current_penalty += curr_pen

        for v in violations:
            v_type = str(v.get("viol_type") or "Unknown").strip()
            std = str(v.get("standard") or "").strip()
            violation_types[v_type] += 1
            if std:
                cited_standards[std] += 1

        compact_inspections.append(
            {
                "activity_nr": item.get("activity_nr"),
                "estab_name": item.get("estab_name"),
                "city_state": f"{item.get('site_city', '')}, {state_code}".strip(", "),
                "open_date": item.get("open_date"),
                "insp_type": item.get("insp_type"),
                "naics_code": item.get("naics_code"),
                "violation_count": v_count,
                "current_penalty_usd": round(curr_pen, 2),
            }
        )

    return {
        "query": query_params,
        "metrics": {
            "inspections_returned": len(inspections),
            "total_violations": total_violations,
            "total_initial_penalty_usd": round(total_initial_penalty, 2),
            "total_current_penalty_usd": round(total_current_penalty, 2),
            "violation_types": dict(violation_types.most_common(10)),
            "top_cited_standards": [
                {"standard": std, "count": cnt}
                for std, cnt in cited_standards.most_common(10)
            ],
            "states_breakdown": dict(states_seen.most_common(15)),
        },
        "inspections_digest": compact_inspections[:50],
    }

"""Unit tests for the DOL OSHA client and Actor helpers."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

ACTOR_ROOT = Path(__file__).resolve().parent.parent
if str(ACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ACTOR_ROOT))

from src.dol_client import (  # noqa: E402
    DolApiError,
    DolOshaClient,
    _extract_records,
    _safe_float,
    build_inspection_filters,
    build_mcp_summary,
)
from src.main import ActorInput, _load_local_env  # noqa: E402


async def _make_client(handler, api_key: str = "test-key") -> DolOshaClient:
    """Create a DolOshaClient backed by an httpx.MockTransport."""
    client = DolOshaClient(api_key=api_key)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Accept": "application/json"},
    )
    return client


def test_build_inspection_filters_empty() -> None:
    assert build_inspection_filters() is None


def test_build_inspection_filters_single() -> None:
    assert build_inspection_filters(state="tx") == {
        "field": "site_state",
        "operator": "eq",
        "value": "TX",
    }


def test_build_inspection_filters_multiple() -> None:
    result = build_inspection_filters(
        establishment_name=" Amazon ",
        state=" ca ",
        naics_code="493110",
        open_date_from="2024-01-01",
        open_date_to="2025-12-31",
    )
    assert result == {
        "and": [
            {"field": "estab_name", "operator": "like", "value": "%AMAZON%"},
            {"field": "site_state", "operator": "eq", "value": "CA"},
            {"field": "naics_code", "operator": "like", "value": "493110%"},
            {"field": "open_date", "operator": "gte", "value": "2024-01-01"},
            {"field": "open_date", "operator": "lte", "value": "2025-12-31"},
        ]
    }


def test_extract_records_shapes() -> None:
    assert _extract_records([{"a": 1}, "bad"]) == [{"a": 1}]
    assert _extract_records({"data": [{"b": 2}]}) == [{"b": 2}]
    assert _extract_records({"d": {"results": [{"c": 3}]}}) == [{"c": 3}]
    assert _extract_records({"d": [{"d": 4}]}) == [{"d": 4}]
    assert _extract_records({"unknown": 123}) == []
    assert _extract_records("not-a-container") == []


def test_safe_float() -> None:
    assert _safe_float(10) == 10.0
    assert _safe_float(12.5) == 12.5
    assert _safe_float("$16,131.50") == 16131.50
    assert _safe_float("") == 0.0
    assert _safe_float(None) == 0.0
    assert _safe_float("N/A") == 0.0


def test_fetch_inspections_auth_sort_pagination_and_cap() -> None:
    seen_calls: list[tuple[int, int, str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-API-KEY" not in request.headers
        assert request.url.params["X-API-KEY"] == "test-key"
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        seen_calls.append(
            (
                limit,
                offset,
                request.url.params["X-API-KEY"],
                request.url.params.get("sort_by"),
                request.url.params.get("sort"),
            )
        )
        if offset == 0:
            rows = [{"activity_nr": i} for i in range(limit)]
        else:
            rows = [{"activity_nr": offset + i} for i in range(min(30, limit))]
        return httpx.Response(200, json={"data": rows})

    async def _run() -> list[dict]:
        async with await _make_client(handler) as client:
            return await client.fetch_inspections(state="TX", max_records=250)

    records = asyncio.run(_run())
    assert len(records) == 230
    assert seen_calls == [
        (200, 0, "test-key", "open_date", "desc"),
        (50, 200, "test-key", "open_date", "desc"),
    ]

    seen_calls.clear()

    def full_pages_handler(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        seen_calls.append(
            (
                limit,
                offset,
                request.url.params["X-API-KEY"],
                request.url.params.get("sort_by"),
                request.url.params.get("sort"),
            )
        )
        rows = [{"activity_nr": offset + i} for i in range(limit)]
        return httpx.Response(200, json={"data": rows})

    async def _run_capped() -> list[dict]:
        async with await _make_client(full_pages_handler) as client:
            return await client.fetch_inspections(state="TX", max_records=210)

    capped = asyncio.run(_run_capped())
    assert len(capped) == 210
    assert seen_calls == [
        (200, 0, "test-key", "open_date", "desc"),
        (10, 200, "test-key", "open_date", "desc"),
    ]


def test_get_page_204_retries_and_redacts_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    attempts = 0

    def empty_204_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["X-API-KEY"] == "test-key"
        return httpx.Response(204)

    async def _run_204() -> list[dict]:
        async with await _make_client(empty_204_handler) as client:
            return await client._get_page("OSHA/inspection/json", limit=10, offset=0)

    assert asyncio.run(_run_204()) == []

    def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        assert "X-API-KEY" not in request.headers
        assert request.url.params["X-API-KEY"] == "test-key"
        if attempts == 1:
            return httpx.Response(429, text="rate limit")
        return httpx.Response(200, json=[{"activity_nr": "999"}])

    async def _run_retry() -> list[dict]:
        async with await _make_client(retry_handler) as client:
            return await client._get_page("OSHA/inspection/json", limit=10, offset=0)

    assert asyncio.run(_run_retry()) == [{"activity_nr": "999"}]
    assert attempts == 2

    secret = "sec+ret/key=1"

    def forbidden_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text=f"Forbidden for {secret} at {request.url}",
        )

    async def _run_403() -> None:
        async with await _make_client(forbidden_handler, api_key=secret) as client:
            await client._get_page("OSHA/inspection/json", limit=10, offset=0)

    with pytest.raises(DolApiError, match="HTTP 403") as exc_info:
        asyncio.run(_run_403())
    msg = str(exc_info.value)
    assert secret not in msg
    assert "sec%2Bret" not in msg
    assert "***" in msg


def test_get_page_retry_after_and_exhausted_429_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_sleeps: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        recorded_sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _record_sleep)
    secret = "rate-limit-secret-key"

    def always_429_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "7"},
            text=f"Too many requests for {secret}",
        )

    async def _run_exhausted() -> None:
        async with await _make_client(always_429_handler, api_key=secret) as client:
            await client._get_page("OSHA/inspection/json", limit=10, offset=0)

    with pytest.raises(DolApiError, match="HTTP 429") as exc_info:
        asyncio.run(_run_exhausted())

    assert recorded_sleeps == [7.0, 7.0]
    err_msg = str(exc_info.value)
    assert "Too many requests for ***" in err_msg
    assert secret not in err_msg
    assert not err_msg.endswith("None")


def test_enrich_inspections_batched_in_and_pagination() -> None:
    seen_filters: list[dict] = []
    seen_offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["X-API-KEY"] == "test-key"
        filt = json.loads(request.url.params["filter_object"])
        offset = int(request.url.params["offset"])
        seen_filters.append(filt)
        seen_offsets.append(offset)
        assert filt["operator"] == "in"
        assert filt["field"] == "activity_nr"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "activity_nr": 1001,
                        "viol_type": "S",
                        "standard": "19100178",
                        "initial_penalty": 10000.0,
                        "current_penalty": 7500.0,
                    },
                    {
                        "activity_nr": 1001,
                        "viol_type": "O",
                        "standard": "19100022",
                        "initial_penalty": "1500.50",
                        "current_penalty": None,
                    },
                    {
                        "activity_nr": 1002,
                        "viol_type": "R",
                        "standard": "19100303 G02    I",
                        "initial_penalty": "$2,000.00",
                        "current_penalty": "$1,200.25",
                    },
                ]
            },
        )

    inspections = [
        {"activity_nr": 1001, "estab_name": "ACME CORP", "site_state": "TX"},
        {"activity_nr": "1002", "estab_name": "BETA LLC", "site_state": "TX"},
        {"activity_nr": "", "estab_name": "NO ACTIVITY"},
    ]

    async def _run() -> list[dict]:
        async with await _make_client(handler) as client:
            return await client.enrich_inspections_with_violations(inspections)

    enriched = asyncio.run(_run())
    assert len(seen_filters) == 1
    assert seen_filters[0]["value"] == ["1001", "1002"]
    assert seen_offsets == [0]
    assert enriched[0]["violation_count"] == 2
    assert enriched[0]["total_initial_penalty"] == 11500.50
    assert enriched[0]["total_current_penalty"] == 7500.0
    assert enriched[1]["violation_count"] == 1
    assert enriched[1]["total_current_penalty"] == 1200.25
    assert enriched[2]["violation_count"] == 0
    assert enriched[2]["violations"] == []

    # Verify multi-page pagination (>200 violations in one batched chunk)
    page_calls: list[int] = []

    def paginated_handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        page_calls.append(offset)
        if offset == 0:
            rows = [{"activity_nr": 1001, "viol_type": "S"} for _ in range(200)]
        else:
            rows = [{"activity_nr": 1002, "viol_type": "O"} for _ in range(15)]
        return httpx.Response(200, json={"data": rows})

    async def _run_paginated() -> dict[str, list[dict]]:
        async with await _make_client(paginated_handler) as client:
            return await client.fetch_violations_for_activities(["1001", "1002", "1001"])

    grouped = asyncio.run(_run_paginated())
    assert page_calls == [0, 200]
    assert len(grouped["1001"]) == 200
    assert len(grouped["1002"]) == 15


def test_build_mcp_summary() -> None:
    inspections = [
        {
            "activity_nr": 1001,
            "estab_name": "ACME CORP",
            "site_city": "Austin",
            "site_state": "TX",
            "open_date": "2025-05-01T00:00:00",
            "insp_type": "C",
            "naics_code": "493110",
            "violation_count": 2,
            "total_initial_penalty": 11500.5,
            "total_current_penalty": 8700.25,
            "violations": [
                {"viol_type": "S", "standard": "19100303 G02    I"},
                {"viol_type": "S", "standard": "19100022"},
            ],
        },
        {
            "activity_nr": 1002,
            "estab_name": "BETA LLC",
            "site_city": "Dallas",
            "site_state": "TX",
            "open_date": "2025-06-10T00:00:00",
            "insp_type": "P",
            "naics_code": "493110",
            "violation_count": 1,
            "total_initial_penalty": 5000.0,
            "total_current_penalty": 5000.0,
            "violations": [{"viol_type": "R", "standard": "19100303  G02 I"}],
        },
    ]
    summary = build_mcp_summary(
        inspections,
        query_params={"establishmentName": "ACME", "state": "TX"},
    )
    assert summary["metrics"]["inspections_returned"] == 2
    assert summary["metrics"]["total_violations"] == 3
    assert summary["metrics"]["total_initial_penalty_usd"] == 16500.5
    assert summary["metrics"]["total_current_penalty_usd"] == 13700.25
    assert summary["metrics"]["violation_types"] == {"S": 2, "R": 1}
    assert summary["metrics"]["top_cited_standards"][0] == {
        "standard": "19100303 G02 I",
        "count": 2,
    }
    assert summary["metrics"]["states_breakdown"] == {"TX": 2}
    assert summary["inspections_digest"][0]["city_state"] == "Austin, TX"
    assert summary["inspections_digest"][0]["open_date"] == "2025-05-01"


def test_actor_input_and_load_local_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = ActorInput(state=" tx ", outputMode="mcp_summary", maxRecords=10)
    assert cfg.state == "TX"
    assert cfg.outputMode == "mcp_summary"

    placeholder_env = tmp_path / "placeholder.env"
    placeholder_env.write_text(
        "# comment\nDOL_API_KEY=replace_with_your_free_dol_api_key\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DOL_API_KEY", raising=False)
    _load_local_env(placeholder_env)
    assert "DOL_API_KEY" not in os.environ

    real_env = tmp_path / "real.env"
    real_env.write_text(
        'DOL_API_KEY="abc-123"\nDOL_API_BASE_URL=https://apiprod.dol.gov/v4/get\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DOL_API_BASE_URL", "https://existing.example")
    _load_local_env(real_env)
    assert os.environ["DOL_API_KEY"] == "abc-123"
    assert os.environ["DOL_API_BASE_URL"] == "https://existing.example"

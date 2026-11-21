"""Official U.S. FDA openFDA Enforcement REST API client & recall risk classifier."""

from __future__ import annotations

import asyncio
import re
import ssl
from typing import Any, Literal

import certifi
import httpx
from pydantic import BaseModel, Field

DomainChoice = Literal["all", "device", "drug", "food"]
SingleDomain = Literal["device", "drug", "food"]

OPENFDA_ENDPOINTS: dict[SingleDomain, str] = {
    "device": "https://api.fda.gov/device/enforcement.json",
    "drug": "https://api.fda.gov/drug/enforcement.json",
    "food": "https://api.fda.gov/food/enforcement.json",
}

USER_AGENT = "USPublicDataActors-OpenFDA-MCP/0.1 (contact: ferrazmichel@gmail.com)"


class OpenFdaApiError(RuntimeError):
    """Raised when the openFDA API returns a non-404 HTTP or network error."""


class FdaRecallRecord(BaseModel):
    """Normalized U.S. FDA enforcement recall record enriched with risk level and metadata."""

    recallNumber: str
    eventId: str | None = None
    domain: SingleDomain
    riskLevel: Literal["CRITICAL", "HIGH", "MODERATE", "LOW"]
    classification: str
    status: str
    voluntaryOrMandated: str
    recallingFirm: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    reportDate: str | None = None
    initiationDate: str | None = None
    classificationDate: str | None = None
    terminationDate: str | None = None
    productType: str | None = None
    productDescription: str
    productQuantity: str | None = None
    reasonForRecall: str
    distributionPattern: str | None = None
    codeInfo: str | None = None
    brandNames: list[str] = Field(default_factory=list)
    genericNames: list[str] = Field(default_factory=list)
    manufacturerNames: list[str] = Field(default_factory=list)
    deviceNames: list[str] = Field(default_factory=list)
    medicalSpecialties: list[str] = Field(default_factory=list)
    productNdcs: list[str] = Field(default_factory=list)
    openFdaPortalUrl: str


def normalize_fda_date(raw_date: Any) -> str | None:
    """Convert openFDA YYYYMMDD date strings into ISO YYYY-MM-DD."""
    text = str(raw_date or "").strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    return None


def classify_recall_risk(
    *,
    classification: str,
    status: str,
    distribution_pattern: str | None = None,
    voluntary_mandated: str | None = None,
) -> Literal["CRITICAL", "HIGH", "MODERATE", "LOW"]:
    """Assign an actionable risk verdict based on FDA classification, status, and distribution."""
    cls_norm = classification.strip().upper()
    status_norm = status.strip().lower()
    dist_norm = (distribution_pattern or "").lower()
    vol_norm = (voluntary_mandated or "").lower()

    if cls_norm == "CLASS I":
        return "CRITICAL" if status_norm == "ongoing" else "HIGH"

    if cls_norm == "CLASS II":
        if status_norm == "ongoing" and (
            "nationwide" in dist_norm
            or "us" in dist_norm.split()
            or "mandated" in vol_norm
            or "fda ordered" in vol_norm
        ):
            return "HIGH"
        return "MODERATE"

    return "LOW"


def build_lucene_search(
    *,
    search_query: str | None = None,
    recalling_firm: str | None = None,
    classification: str = "ALL",
    status: str = "ALL",
    state: str | None = None,
    report_date_from: str | None = None,
) -> str | None:
    """Build an openFDA Lucene `search=` expression from structured query parameters."""
    clauses: list[str] = []

    if classification and classification.upper() != "ALL":
        clean_cls = classification.replace('"', "").strip()
        clauses.append(f'classification:"{clean_cls}"')

    if status and status.upper() != "ALL":
        clean_status = status.replace('"', "").strip()
        clauses.append(f'status:"{clean_status}"')

    if recalling_firm and recalling_firm.strip():
        clean_firm = recalling_firm.replace('"', "").strip()
        clauses.append(f'recalling_firm:"{clean_firm}"')

    if state and state.strip():
        clean_state = state.replace('"', "").strip().upper()
        clauses.append(f'state:"{clean_state}"')

    if report_date_from and report_date_from.strip():
        digits = re.sub(r"\D", "", report_date_from.strip())
        if len(digits) == 8:
            clauses.append(f"report_date:[{digits} TO 20991231]")

    if search_query and search_query.strip():
        clean_q = search_query.replace('"', "").strip()
        clauses.append(
            f'(product_description:"{clean_q}" OR reason_for_recall:"{clean_q}" '
            f'OR openfda.brand_name:"{clean_q}" OR openfda.device_name:"{clean_q}")'
        )

    return " AND ".join(clauses) if clauses else None


def _clean_str_list(openfda_obj: Any, key: str, limit: int = 8) -> list[str]:
    if not isinstance(openfda_obj, dict):
        return []
    val = openfda_obj.get(key)
    if not isinstance(val, list):
        return []
    out: list[str] = []
    for item in val:
        txt = str(item or "").strip()
        if txt and txt not in out:
            out.append(txt)
        if len(out) >= limit:
            break
    return out


class OpenFdaClient:
    """Async client for U.S. FDA openFDA Enforcement REST APIs."""

    def __init__(self, timeout_seconds: float = 25.0) -> None:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            verify=ssl_context,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

    async def __aenter__(self) -> OpenFdaClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client session."""
        await self._client.aclose()

    async def _fetch_domain(
        self,
        domain: SingleDomain,
        search_expr: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query a single openFDA enforcement domain, treating HTTP 404 as 0 results."""
        endpoint = OPENFDA_ENDPOINTS[domain]
        params: dict[str, Any] = {
            "sort": "report_date:desc",
            "limit": min(max(limit, 1), 100),
        }
        if search_expr:
            params["search"] = search_expr

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self._client.get(endpoint, params=params)
                if resp.status_code == 404:
                    # openFDA returns 404 NOT_FOUND when a valid Lucene query matches 0 rows
                    return []
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.8 * (2**attempt))
                    continue
                resp.raise_for_status()
                payload = resp.json()
                results = payload.get("results", [])
                if not isinstance(results, list):
                    return []
                return results
            except httpx.HTTPError as exc:
                last_err = exc
                if attempt < 2:
                    await asyncio.sleep(0.8 * (2**attempt))
                    continue

        raise OpenFdaApiError(
            f"openFDA {domain} enforcement request failed: {last_err}"
        ) from last_err

    @staticmethod
    def _normalize_row(row: dict[str, Any], domain: SingleDomain) -> FdaRecallRecord:
        classification = str(row.get("classification") or "Unknown").strip()
        status = str(row.get("status") or "Unknown").strip()
        distribution = str(row.get("distribution_pattern") or "").strip() or None
        voluntary = str(row.get("voluntary_mandated") or "Unknown").strip()
        openfda = row.get("openfda") or {}
        recall_number = str(row.get("recall_number") or row.get("event_id") or "N/A").strip()

        return FdaRecallRecord(
            recallNumber=recall_number,
            eventId=str(row.get("event_id") or "").strip() or None,
            domain=domain,
            riskLevel=classify_recall_risk(
                classification=classification,
                status=status,
                distribution_pattern=distribution,
                voluntary_mandated=voluntary,
            ),
            classification=classification,
            status=status,
            voluntaryOrMandated=voluntary,
            recallingFirm=str(row.get("recalling_firm") or "Unknown").strip(),
            city=str(row.get("city") or "").strip() or None,
            state=str(row.get("state") or "").strip() or None,
            country=str(row.get("country") or "").strip() or None,
            reportDate=normalize_fda_date(row.get("report_date")),
            initiationDate=normalize_fda_date(row.get("recall_initiation_date")),
            classificationDate=normalize_fda_date(row.get("center_classification_date")),
            terminationDate=normalize_fda_date(row.get("termination_date")),
            productType=str(row.get("product_type") or "").strip() or None,
            productDescription=str(row.get("product_description") or "").strip(),
            productQuantity=str(row.get("product_quantity") or "").strip() or None,
            reasonForRecall=str(row.get("reason_for_recall") or "").strip(),
            distributionPattern=distribution,
            codeInfo=str(row.get("code_info") or "").strip() or None,
            brandNames=_clean_str_list(openfda, "brand_name"),
            genericNames=_clean_str_list(openfda, "generic_name"),
            manufacturerNames=_clean_str_list(openfda, "manufacturer_name"),
            deviceNames=_clean_str_list(openfda, "device_name"),
            medicalSpecialties=_clean_str_list(openfda, "medical_specialty_description"),
            productNdcs=_clean_str_list(openfda, "product_ndc"),
            openFdaPortalUrl=f"https://www.accessdata.fda.gov/scripts/ires/?Event={row.get('event_id', '')}",
        )

    async def search_recalls(
        self,
        *,
        domain: DomainChoice = "all",
        search_query: str | None = None,
        recalling_firm: str | None = None,
        classification: str = "Class I",
        status: str = "Ongoing",
        state: str | None = None,
        report_date_from: str | None = None,
        max_records: int = 15,
    ) -> list[FdaRecallRecord]:
        """Search one or all FDA enforcement domains and return sorted normalized records."""
        search_expr = build_lucene_search(
            search_query=search_query,
            recalling_firm=recalling_firm,
            classification=classification,
            status=status,
            state=state,
            report_date_from=report_date_from,
        )

        target_domains: list[SingleDomain] = (
            ["device", "drug", "food"] if domain == "all" else [domain]
        )

        per_domain_limit = max_records if len(target_domains) == 1 else min(100, max_records)
        responses = await asyncio.gather(
            *(self._fetch_domain(d, search_expr, per_domain_limit) for d in target_domains)
        )

        merged: list[FdaRecallRecord] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for dom, rows in zip(target_domains, responses):
            for row in rows:
                rec = self._normalize_row(row, dom)
                dedupe_key = (rec.domain, rec.recallNumber, rec.productDescription[:80])
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                merged.append(rec)

        merged.sort(key=lambda r: (r.reportDate or "", r.recallNumber), reverse=True)
        return merged[:max_records]


def build_mcp_summary(
    records: list[FdaRecallRecord],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Generate a compact, token-efficient MCP recall radar summary for AI agents."""
    if not records:
        return {
            "title": "openFDA Recall & Enforcement Radar MCP Summary",
            "overall_alert_level": "NONE_MATCHED",
            "criteria": criteria,
            "metrics": {
                "total_recalls": 0,
                "critical_class_i_ongoing": 0,
            },
            "alerts": [],
        }

    risk_breakdown = {"CRITICAL": 0, "HIGH": 0, "MODERATE": 0, "LOW": 0}
    domain_breakdown: dict[str, int] = {}
    class_breakdown: dict[str, int] = {}
    firm_counts: dict[str, int] = {}

    for rec in records:
        risk_breakdown[rec.riskLevel] = risk_breakdown.get(rec.riskLevel, 0) + 1
        domain_breakdown[rec.domain] = domain_breakdown.get(rec.domain, 0) + 1
        class_breakdown[rec.classification] = class_breakdown.get(rec.classification, 0) + 1
        firm_counts[rec.recallingFirm] = firm_counts.get(rec.recallingFirm, 0) + 1

    if risk_breakdown["CRITICAL"] > 0:
        overall = "CRITICAL_RECALLS_DETECTED"
    elif risk_breakdown["HIGH"] > 0:
        overall = "HIGH_RISK_RECALLS_DETECTED"
    elif risk_breakdown["MODERATE"] > 0:
        overall = "MODERATE_RECALLS_DETECTED"
    else:
        overall = "LOW_RISK_ONLY"

    top_firms = [
        {"firm": firm, "recall_count": count}
        for firm, count in sorted(firm_counts.items(), key=lambda x: (-x[1], x[0]))[:10]
    ]

    compact_alerts = [
        {
            "recall_number": r.recallNumber,
            "domain": r.domain,
            "risk_level": r.riskLevel,
            "classification": r.classification,
            "status": r.status,
            "recalling_firm": r.recallingFirm,
            "state": r.state,
            "report_date": r.reportDate,
            "product_summary": r.productDescription[:140],
            "reason_summary": r.reasonForRecall[:140],
        }
        for r in records[:15]
    ]

    return {
        "title": "openFDA Recall & Enforcement Radar MCP Summary",
        "overall_alert_level": overall,
        "criteria": criteria,
        "metrics": {
            "total_recalls": len(records),
            "risk_breakdown": risk_breakdown,
            "domain_breakdown": domain_breakdown,
            "class_breakdown": class_breakdown,
            "ongoing_recalls": sum(1 for r in records if r.status.lower() == "ongoing"),
        },
        "top_recalling_firms": top_firms,
        "alerts": compact_alerts,
    }

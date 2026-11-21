"""HTTP Client and data models for US EPA ECHO REST Services."""

from __future__ import annotations

import re
from typing import Any
import httpx
from pydantic import BaseModel, Field

DEFAULT_ECHO_BASE_URL = "https://echodata.epa.gov/echo/echo_rest_services"


def _parse_currency(value: Any) -> float:
    """Parse monetary string like '$1,250' or '$0' to float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_int(value: Any, default: int = 0) -> int:
    """Parse integer or return default."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class EpaFacility(BaseModel):
    """Standardized regulated facility record from EPA ECHO."""

    registry_id: str
    facility_name: str
    street_address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    county: str | None = None
    sic_codes: str | None = None
    sic_descriptions: str | None = None
    naics_codes: str | None = None
    compliance_status: str = "Unknown"
    has_significant_non_compliance: bool = False
    quarters_in_non_compliance: int = 0
    clean_air_act_status: str | None = None
    clean_water_act_status: str | None = None
    rcra_hazardous_waste_status: str | None = None
    sdwa_drinking_water_status: str | None = None
    inspection_count: int = 0
    days_last_inspection: int | None = None
    date_last_inspection: str | None = None
    formal_enforcement_action_count: int = 0
    total_penalties: float = 0.0
    active_programs: list[str] = Field(default_factory=list)
    echo_report_url: str

    @classmethod
    def from_raw_api(cls, raw: dict[str, Any]) -> EpaFacility:
        """Parse raw EPA ECHO API dictionary into clean model."""
        registry_id = str(raw.get("RegistryID") or "").strip()
        fac_name = str(raw.get("FacName") or "Unknown Facility").strip()

        # Derive active environmental media programs
        programs = []
        if raw.get("CAAComplianceStatus") or raw.get("CAARows"):
            programs.append("CAA (Air)")
        if raw.get("CWAComplianceStatus") or raw.get("CWAPermitTypes"):
            programs.append("CWA (Water)")
        if raw.get("RCRAComplianceStatus") or raw.get("RCRAPermitTypes"):
            programs.append("RCRA (Waste)")
        if raw.get("SDWAComplianceStatus") or raw.get("SDWASystemTypes"):
            programs.append("SDWA (Drinking Water)")

        snc_flag = str(raw.get("FacSNCFlg") or "").strip().upper() == "Y"
        penalties = _parse_currency(raw.get("FacTotalPenalties"))
        days_insp = raw.get("FacDaysLastInspection")
        parsed_days = _parse_int(days_insp, default=-1) if days_insp is not None else None
        if parsed_days == -1:
            parsed_days = None

        return cls(
            registry_id=registry_id,
            facility_name=fac_name,
            street_address=raw.get("FacStreet") or None,
            city=raw.get("FacCity") or None,
            state=raw.get("FacState") or None,
            zip_code=raw.get("FacZip") or None,
            county=raw.get("FacCounty") or None,
            sic_codes=raw.get("FacSICCodes") or None,
            sic_descriptions=raw.get("FacSICDescs") or None,
            naics_codes=raw.get("FacNAICSCodes") or None,
            compliance_status=str(raw.get("FacComplianceStatus") or "No Violation Identified").strip(),
            has_significant_non_compliance=snc_flag,
            quarters_in_non_compliance=_parse_int(raw.get("FacQtrsWithNC")),
            clean_air_act_status=raw.get("CAAComplianceStatus") or None,
            clean_water_act_status=raw.get("CWAComplianceStatus") or None,
            rcra_hazardous_waste_status=raw.get("RCRAComplianceStatus") or None,
            sdwa_drinking_water_status=raw.get("SDWAComplianceStatus") or None,
            inspection_count=_parse_int(raw.get("FacInspectionCount")),
            days_last_inspection=parsed_days,
            date_last_inspection=raw.get("FacDateLastInspection") or None,
            formal_enforcement_action_count=_parse_int(raw.get("FacFormalActionCount")),
            total_penalties=penalties,
            active_programs=programs,
            echo_report_url=f"https://echo.epa.gov/detailed-facility-report?fid={registry_id}",
        )


class EpaEchoClient:
    """Client for EPA ECHO REST Services with 2-step QID resolution."""

    def __init__(
        self,
        base_url: str = DEFAULT_ECHO_BASE_URL,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": "epa-echo-environmental-mcp/0.1 (Apify Actor)"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> EpaEchoClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def search_facilities(
        self,
        facility_name: str | None = None,
        state: str | None = None,
        city: str | None = None,
        zip_code: str | None = None,
        naics_code: str | None = None,
        significant_non_compliance_only: bool = False,
        max_records: int = 50,
    ) -> list[EpaFacility]:
        """Perform 2-step EPA search: get_facilities -> get_qid with pagination."""
        params: dict[str, Any] = {
            "output": "JSON",
        }
        if facility_name:
            params["p_fn"] = facility_name.strip()
        if state:
            params["p_st"] = state.strip().upper()
        if city:
            params["p_ct"] = city.strip()
        if zip_code:
            params["p_zip"] = zip_code.strip()
        if naics_code:
            params["p_ncs"] = naics_code.strip()
        if significant_non_compliance_only:
            params["p_snc"] = "Y"

        # Step 1: Initialize query and obtain QueryID
        init_url = f"{self.base_url}.get_facilities"
        resp = await self._client.get(init_url, params=params)
        resp.raise_for_status()
        data = resp.json()

        results_meta = data.get("Results") or {}
        query_rows = _parse_int(results_meta.get("QueryRows"))
        query_id = results_meta.get("QueryID")

        if query_rows == 0 or not query_id:
            return []

        # Step 2: Fetch facilities using QueryID
        facilities: list[EpaFacility] = []
        page_no = 1

        while len(facilities) < max_records:
            qid_url = f"{self.base_url}.get_qid"
            qid_params = {
                "output": "JSON",
                "qid": query_id,
                "pageno": str(page_no),
            }
            qid_resp = await self._client.get(qid_url, params=qid_params)
            qid_resp.raise_for_status()
            qid_data = qid_resp.json()

            page_results = qid_data.get("Results") or {}
            raw_facilities = page_results.get("Facilities") or []
            if not raw_facilities:
                break

            for raw_fac in raw_facilities:
                if len(facilities) >= max_records:
                    break
                facility = EpaFacility.from_raw_api(raw_fac)
                if significant_non_compliance_only and not facility.has_significant_non_compliance:
                    continue
                facilities.append(facility)

            # Check if more pages exist
            total_pages = _parse_int(page_results.get("TotalPages"), default=1)
            if page_no >= total_pages:
                break
            page_no += 1

        return facilities


def build_mcp_summary(
    facilities: list[EpaFacility],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Generate compact executive risk profile for AI agents."""
    total_facilities = len(facilities)
    snc_count = sum(1 for f in facilities if f.has_significant_non_compliance)
    viol_count = sum(1 for f in facilities if f.compliance_status != "No Violation Identified")
    total_penalties = sum(f.total_penalties for f in facilities)
    total_formal_actions = sum(f.formal_enforcement_action_count for f in facilities)

    # Risk level determination
    if snc_count > 0 or total_penalties >= 100_000:
        risk_level = "CRITICAL"
    elif viol_count > 0 or total_formal_actions > 0 or total_penalties > 0:
        risk_level = "HIGH"
    elif any(f.quarters_in_non_compliance > 0 for f in facilities):
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    # Statutes distribution
    statutes: dict[str, int] = {"CAA (Air)": 0, "CWA (Water)": 0, "RCRA (Waste)": 0, "SDWA (Drinking Water)": 0}
    for f in facilities:
        for prog in f.active_programs:
            if prog in statutes:
                statutes[prog] += 1

    # Flag top high risk facilities
    high_risk = []
    for f in facilities:
        if f.has_significant_non_compliance or f.total_penalties > 0 or f.formal_enforcement_action_count > 0:
            high_risk.append({
                "facility_name": f.facility_name,
                "city": f.city,
                "state": f.state,
                "has_snc": f.has_significant_non_compliance,
                "compliance_status": f.compliance_status,
                "total_penalties_usd": f.total_penalties,
                "echo_report_url": f.echo_report_url,
            })

    return {
        "title": "EPA ECHO Environmental Risk Assessment (Executive Summary)",
        "risk_level": risk_level,
        "criteria": criteria,
        "metrics": {
            "total_facilities_analyzed": total_facilities,
            "facilities_with_significant_non_compliance": snc_count,
            "facilities_with_active_violations": viol_count,
            "total_formal_enforcement_actions": total_formal_actions,
            "total_penalties_assessed_usd": round(total_penalties, 2),
            "environmental_statutes_coverage": statutes,
        },
        "flagged_high_risk_facilities": high_risk[:5],
    }


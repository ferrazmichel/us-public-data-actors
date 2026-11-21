"""HTTP client, risk vetting engine, and data models for USDOT/FMCSA Socrata APIs."""

from __future__ import annotations

import asyncio
import re
import ssl
from datetime import date, datetime, timezone
from typing import Any, Literal

import certifi
import httpx
from pydantic import BaseModel, Field

CENSUS_URL = "https://data.transportation.gov/resource/az4n-8mr2.json"
AUTHORITY_URL = "https://data.transportation.gov/resource/6eyk-hxee.json"
INSURANCE_URL = "https://data.transportation.gov/resource/qh9u-swkp.json"

SAFER_URL_TEMPLATE = (
    "https://safer.fmcsa.dot.gov/query.asp"
    "?searchtype=ANY&query_type=queryCarrierSnapshot&query_param=USDOT&query_string={dot}"
)

SAFETY_RATING_MAP: dict[str, Literal["Satisfactory", "Conditional", "Unsatisfactory", "Unrated"]] = {
    "S": "Satisfactory",
    "C": "Conditional",
    "U": "Unsatisfactory",
}

CARGO_FIELD_MAP: dict[str, str] = {
    "crgo_genfreight": "General Freight",
    "crgo_household": "Household Goods",
    "crgo_metalsheet": "Metal: Sheets, Coils, Rolls",
    "crgo_motoveh": "Motor Vehicles",
    "crgo_drivetow": "Drive/Tow Away",
    "crgo_logpole": "Logs, Poles, Beams, Lumber",
    "crgo_bldgmat": "Building Materials",
    "crgo_mobilehome": "Mobile Homes",
    "crgo_machlrg": "Machinery, Large Objects",
    "crgo_produce": "Fresh Produce",
    "crgo_liqgas": "Liquids/Gases",
    "crgo_intermodal": "Intermodal Containers",
    "crgo_passengers": "Passengers",
    "crgo_oilfield": "Oilfield Equipment",
    "crgo_livestock": "Livestock",
    "crgo_grainfeed": "Grain, Feed, Hay",
    "crgo_coalcoke": "Coal/Coke",
    "crgo_meat": "Meat",
    "crgo_garbage": "Garbage/Refuse",
    "crgo_usmail": "US Mail",
    "crgo_chem": "Chemicals",
    "crgo_drybulk": "Commodities Dry Bulk",
    "crgo_coldfood": "Refrigerated Food",
    "crgo_beverages": "Beverages",
    "crgo_paperprod": "Paper Products",
    "crgo_utility": "Utilities",
    "crgo_farmsupp": "Farm Supplies",
    "crgo_construct": "Construction",
    "crgo_waterwell": "Water Well",
    "crgo_cargoothr": "Other Cargo",
}

VettingVerdict = Literal["PASS", "CAUTION", "HIGH_RISK", "DO_NOT_USE"]


def _clean_digits(value: str | None) -> str:
    """Extract digits and strip leading zeros for USDOT / MC docket lookups."""
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""
    return digits.lstrip("0") or "0"


def _parse_int(value: Any, default: int = 0) -> int:
    """Parse integer safely from string or numeric field."""
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def _parse_float(value: Any, default: float | None = None) -> float | None:
    """Parse float safely from string or numeric field."""
    if value is None or value == "":
        return default
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default


def _format_yyyymmdd(raw: Any) -> str | None:
    """Normalize 'YYYYMMDD' or 'YYYY-MM-DD' into ISO 'YYYY-MM-DD'."""
    if not raw:
        return None
    text = str(raw).strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    return text or None


def _escape_soql(value: str) -> str:
    """Escape single quotes for Socrata SoQL string literals."""
    return value.replace("'", "''")


def _extract_cargo_types(raw: dict[str, Any]) -> list[str]:
    """Convert crgo_* == 'X' flags into human-readable cargo labels."""
    cargo: list[str] = []
    for field, label in CARGO_FIELD_MAP.items():
        if str(raw.get(field) or "").strip().upper() == "X":
            if field == "crgo_cargoothr":
                other_desc = str(raw.get("crgo_cargoothr_desc") or "").strip()
                cargo.append(other_desc if other_desc else label)
            else:
                cargo.append(label)
    return cargo


def _parse_safety_rating(raw_code: Any) -> Literal["Satisfactory", "Conditional", "Unsatisfactory", "Unrated"]:
    code = str(raw_code or "").strip().upper()
    return SAFETY_RATING_MAP.get(code, "Unrated")


class FmcsaApiError(RuntimeError):
    """Raised when USDOT/FMCSA Socrata endpoints fail unexpectedly."""


class InsurancePolicy(BaseModel):
    """Active or pending insurance policy record from FMCSA Insurance dataset."""

    docket_number: str | None = None
    form_code: str | None = None
    insurance_type: str | None = None
    insurer_name: str | None = None
    policy_number: str | None = None
    max_coverage_usd: int = 0
    underlying_limit_usd: int = 0
    effective_date: str | None = None
    cancel_effective_date: str | None = None


class FmcsaCarrier(BaseModel):
    """Normalized motor carrier vetting and lead profile from official USDOT/FMCSA data."""

    dot_number: str
    mc_number: str | None = None
    legal_name: str
    dba_name: str | None = None
    status_code: str = "Unknown"
    add_date: str | None = None
    mcs150_date: str | None = None
    carrier_operation: str | None = None
    classdef: str | None = None
    business_org_desc: str | None = None

    company_officer_1: str | None = None
    company_officer_2: str | None = None
    phone: str | None = None
    cell_phone: str | None = None
    email_address: str | None = None
    phy_street: str | None = None
    phy_city: str | None = None
    phy_state: str | None = None
    phy_zip: str | None = None

    power_units: int = 0
    truck_units: int = 0
    bus_units: int = 0
    total_drivers: int = 0
    total_cdl: int = 0
    mcs150_mileage: int = 0
    cargo_carried: list[str] = Field(default_factory=list)
    is_hazmat: bool = False

    safety_rating: Literal["Satisfactory", "Conditional", "Unsatisfactory", "Unrated"] = "Unrated"
    safety_rating_date: str | None = None
    recordable_crash_rate: float | None = None
    prior_revoke_flag: bool = False

    authority_checked: bool = False
    common_authority_status: str | None = None
    contract_authority_status: str | None = None
    broker_authority_status: str | None = None
    pending_revocation: bool = False

    bipd_required_usd: int = 0
    bipd_on_file_usd: int = 0
    cargo_insurance_on_file: bool | None = None
    bond_on_file: bool | None = None
    active_insurers: list[InsurancePolicy] = Field(default_factory=list)

    vetting_verdict: VettingVerdict = "PASS"
    risk_flags: list[str] = Field(default_factory=list)
    safer_url: str

    @classmethod
    def from_census_row(cls, raw: dict[str, Any]) -> FmcsaCarrier:
        """Build normalized carrier model from an az4n-8mr2 Company Census row."""
        dot_number = _clean_digits(str(raw.get("dot_number") or ""))
        docket_prefix = str(raw.get("docket1prefix") or "").strip().upper()
        docket_num = str(raw.get("docket1") or "").strip()
        mc_number = f"{docket_prefix}-{docket_num}" if docket_num and docket_prefix else (docket_num or None)

        carrier = cls(
            dot_number=dot_number,
            mc_number=mc_number,
            legal_name=str(raw.get("legal_name") or "Unknown Carrier").strip(),
            dba_name=(str(raw.get("dba_name")).strip() if raw.get("dba_name") else None),
            status_code=str(raw.get("status_code") or "Unknown").strip().upper(),
            add_date=_format_yyyymmdd(raw.get("add_date")),
            mcs150_date=_format_yyyymmdd(raw.get("mcs150_date")),
            carrier_operation=(str(raw.get("carrier_operation")).strip() if raw.get("carrier_operation") else None),
            classdef=(str(raw.get("classdef")).strip() if raw.get("classdef") else None),
            business_org_desc=(str(raw.get("business_org_desc")).strip() if raw.get("business_org_desc") else None),
            company_officer_1=(str(raw.get("company_officer_1")).strip() if raw.get("company_officer_1") else None),
            company_officer_2=(str(raw.get("company_officer_2")).strip() if raw.get("company_officer_2") else None),
            phone=(str(raw.get("phone")).strip() if raw.get("phone") else None),
            cell_phone=(str(raw.get("cell_phone")).strip() if raw.get("cell_phone") else None),
            email_address=(str(raw.get("email_address")).strip() if raw.get("email_address") else None),
            phy_street=(str(raw.get("phy_street")).strip() if raw.get("phy_street") else None),
            phy_city=(str(raw.get("phy_city")).strip() if raw.get("phy_city") else None),
            phy_state=(str(raw.get("phy_state")).strip().upper() if raw.get("phy_state") else None),
            phy_zip=(str(raw.get("phy_zip")).strip() if raw.get("phy_zip") else None),
            power_units=_parse_int(raw.get("power_units")),
            truck_units=_parse_int(raw.get("truck_units")),
            bus_units=_parse_int(raw.get("bus_units")),
            total_drivers=_parse_int(raw.get("total_drivers")),
            total_cdl=_parse_int(raw.get("total_cdl")),
            mcs150_mileage=_parse_int(raw.get("mcs150_mileage")),
            cargo_carried=_extract_cargo_types(raw),
            is_hazmat=str(raw.get("hm_ind") or "").strip().upper() == "Y",
            safety_rating=_parse_safety_rating(raw.get("safety_rating")),
            safety_rating_date=_format_yyyymmdd(raw.get("safety_rating_date")),
            recordable_crash_rate=_parse_float(raw.get("recordable_crash_rate")),
            prior_revoke_flag=str(raw.get("prior_revoke_flag") or "").strip().upper() == "Y",
            safer_url=SAFER_URL_TEMPLATE.format(dot=dot_number),
        )
        evaluate_carrier_risk(carrier)
        return carrier


def evaluate_carrier_risk(
    carrier: FmcsaCarrier,
    reference_date: date | None = None,
) -> FmcsaCarrier:
    """Evaluate vetting_verdict and risk_flags deterministically for a carrier profile."""
    flags: list[str] = []
    do_not_use = False
    high_risk = False
    caution = False

    if carrier.status_code != "A":
        do_not_use = True
        flags.append(f"Inactive or non-active USDOT status ({carrier.status_code})")

    if carrier.safety_rating == "Unsatisfactory":
        do_not_use = True
        flags.append("FMCSA Safety Rating: Unsatisfactory")
    elif carrier.safety_rating == "Conditional":
        high_risk = True
        flags.append("FMCSA Safety Rating: Conditional")

    if carrier.pending_revocation:
        do_not_use = True
        flags.append("Pending operating authority revocation in FMCSA L&I")

    if carrier.prior_revoke_flag:
        high_risk = True
        flags.append("Prior operating authority revocation on record")

    if carrier.authority_checked and carrier.bipd_required_usd > 0 and carrier.bipd_on_file_usd < carrier.bipd_required_usd:
        high_risk = True
        flags.append(
            f"BIPD insurance below required minimum (${carrier.bipd_on_file_usd:,} on file vs. ${carrier.bipd_required_usd:,} required)"
        )

    if (
        carrier.authority_checked
        and carrier.classdef
        and "AUTHORIZED FOR HIRE" in carrier.classdef.upper()
        and not any(
            st == "A"
            for st in (
                carrier.common_authority_status,
                carrier.contract_authority_status,
                carrier.broker_authority_status,
            )
        )
    ):
        caution = True
        flags.append("No active Common/Contract/Broker operating authority found in L&I")

    if carrier.add_date:
        try:
            added_dt = datetime.strptime(carrier.add_date, "%Y-%m-%d").date()
            today = reference_date or datetime.now(timezone.utc).date()
            age_days = (today - added_dt).days
            if 0 <= age_days < 90:
                caution = True
                flags.append(f"New authority (< 90 days old: registered {age_days} days ago)")
        except ValueError:
            pass

    if do_not_use:
        carrier.vetting_verdict = "DO_NOT_USE"
    elif high_risk:
        carrier.vetting_verdict = "HIGH_RISK"
    elif caution:
        carrier.vetting_verdict = "CAUTION"
    else:
        carrier.vetting_verdict = "PASS"

    carrier.risk_flags = flags
    return carrier


def _pick_stronger_status(current: str | None, candidate: str | None) -> str | None:
    priority = {"A": 3, "I": 2, "N": 1}
    cand = (candidate or "").strip().upper() or None
    if cand is None:
        return current
    if current is None:
        return cand
    return cand if priority.get(cand, 0) > priority.get(current, 0) else current


class FmcsaClient:
    """Async client for USDOT/FMCSA Socrata Open Data APIs."""

    def __init__(
        self,
        census_url: str = CENSUS_URL,
        authority_url: str = AUTHORITY_URL,
        insurance_url: str = INSURANCE_URL,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.census_url = census_url
        self.authority_url = authority_url
        self.insurance_url = insurance_url
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            verify=ssl.create_default_context(cafile=certifi.where()),
            headers={
                "Accept": "application/json",
                "User-Agent": "fmcsa-carrier-safety-mcp/0.1 (Apify Actor)",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> FmcsaClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _get_json_with_retry(self, url: str, params: dict[str, Any], retries: int = 2) -> list[dict[str, Any]]:
        """GET Socrata JSON array with backoff on transient 429/5xx errors."""
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = await self._client.get(url, params=params)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                if resp.status_code >= 400:
                    raise FmcsaApiError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")
                payload = resp.json()
                if not isinstance(payload, list):
                    raise FmcsaApiError(f"Unexpected non-list response from {url}")
                return payload
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise FmcsaApiError(f"Network error calling {url}: {exc}") from exc
        raise FmcsaApiError(f"Exhausted retries calling {url}: {last_exc}")

    async def search_carriers(
        self,
        dot_number: str | None = None,
        mc_number: str | None = None,
        carrier_name: str | None = None,
        state: str | None = None,
        city: str | None = None,
        status_code: Literal["A", "I", "ALL"] = "A",
        added_after_date: str | None = None,
        min_power_units: int = 0,
        hazmat_only: bool = False,
        include_authority_and_insurance: bool = True,
        max_records: int = 20,
    ) -> list[FmcsaCarrier]:
        """Query Company Census and optionally enrich with L&I Authority and Insurance."""
        where_clauses: list[str] = []

        cleaned_dot = _clean_digits(dot_number)
        cleaned_mc = _clean_digits(mc_number)
        if cleaned_dot:
            where_clauses.append(f"dot_number = '{_escape_soql(cleaned_dot)}'")
        if cleaned_mc:
            where_clauses.append(f"docket1 = '{_escape_soql(cleaned_mc)}'")
        if state:
            where_clauses.append(f"phy_state = '{_escape_soql(state.strip().upper())}'")
        if city:
            where_clauses.append(f"phy_city = '{_escape_soql(city.strip().upper())}'")
        if status_code in ("A", "I") and not cleaned_dot and not cleaned_mc:
            where_clauses.append(f"status_code = '{status_code}'")
        if hazmat_only:
            where_clauses.append("hm_ind = 'Y'")
        if added_after_date:
            normalized_date = added_after_date.strip().replace("-", "")
            if re.fullmatch(r"\d{8}", normalized_date):
                where_clauses.append(f"add_date >= '{normalized_date}'")

        needs_memory_filter = min_power_units > 0 or bool(carrier_name and carrier_name.strip())
        batch_size = min(200, max(max_records * 3, 100)) if needs_memory_filter else max_records
        max_pages = 5 if needs_memory_filter else 1

        carriers: list[FmcsaCarrier] = []
        seen_dots: set[str] = set()
        name_needle = carrier_name.strip().upper() if carrier_name and carrier_name.strip() else ""

        for page_idx in range(max_pages):
            params: dict[str, Any] = {
                "$limit": str(batch_size),
                "$offset": str(page_idx * batch_size),
            }
            if where_clauses:
                params["$where"] = " AND ".join(where_clauses)
            if name_needle:
                params["$q"] = carrier_name.strip()  # type: ignore[union-attr]
            else:
                params["$order"] = "add_date DESC"

            rows = await self._get_json_with_retry(self.census_url, params)
            if not rows:
                break

            for row in rows:
                carrier = FmcsaCarrier.from_census_row(row)
                if not carrier.dot_number or carrier.dot_number in seen_dots:
                    continue
                if min_power_units > 0 and carrier.power_units < min_power_units:
                    continue
                if name_needle:
                    haystack = f"{carrier.legal_name} {carrier.dba_name or ''}".upper()
                    if name_needle not in haystack:
                        continue
                seen_dots.add(carrier.dot_number)
                carriers.append(carrier)
                if len(carriers) >= max_records:
                    break

            if len(carriers) >= max_records or len(rows) < batch_size:
                break

        if include_authority_and_insurance and carriers:
            await self.enrich_authority_and_insurance(carriers)

        return carriers

    async def enrich_authority_and_insurance(self, carriers: list[FmcsaCarrier]) -> None:
        """Batch-fetch L&I authority and insurance policies using 8-digit zero-padded USDOTs."""
        padded_dots = list({c.dot_number.zfill(8) for c in carriers if c.dot_number})
        if not padded_dots:
            return

        auth_by_dot: dict[str, list[dict[str, Any]]] = {}
        ins_by_dot: dict[str, list[dict[str, Any]]] = {}

        for idx in range(0, len(padded_dots), 50):
            chunk = padded_dots[idx : idx + 50]
            in_list = ",".join(f"'{d}'" for d in chunk)
            where_expr = f"dot_number in({in_list})"

            auth_rows, ins_rows = await asyncio.gather(
                self._get_json_with_retry(self.authority_url, {"$where": where_expr, "$limit": "200"}),
                self._get_json_with_retry(self.insurance_url, {"$where": where_expr, "$limit": "500"}),
            )

            for row in auth_rows:
                padded = str(row.get("dot_number") or "").strip().zfill(8)
                if padded:
                    auth_by_dot.setdefault(padded, []).append(row)

            for row in ins_rows:
                padded = str(row.get("dot_number") or "").strip().zfill(8)
                if padded:
                    ins_by_dot.setdefault(padded, []).append(row)

        for carrier in carriers:
            padded = carrier.dot_number.zfill(8)
            auth_rows = auth_by_dot.get(padded, [])
            ins_rows = ins_by_dot.get(padded, [])

            if auth_rows:
                carrier.authority_checked = True
                for row in auth_rows:
                    if not carrier.mc_number and row.get("docket_number"):
                        carrier.mc_number = str(row["docket_number"]).strip()
                    carrier.common_authority_status = _pick_stronger_status(
                        carrier.common_authority_status, row.get("common_stat")
                    )
                    carrier.contract_authority_status = _pick_stronger_status(
                        carrier.contract_authority_status, row.get("contract_stat")
                    )
                    carrier.broker_authority_status = _pick_stronger_status(
                        carrier.broker_authority_status, row.get("broker_stat")
                    )
                    if any(
                        str(row.get(k) or "").strip().upper() == "Y"
                        for k in ("common_rev_pend", "contract_rev_pend", "broker_rev_pend")
                    ):
                        carrier.pending_revocation = True

                    carrier.bipd_required_usd = max(
                        carrier.bipd_required_usd, _parse_int(row.get("min_cov_amount")) * 1000
                    )
                    carrier.bipd_on_file_usd = max(
                        carrier.bipd_on_file_usd, _parse_int(row.get("bipd_file")) * 1000
                    )
                    if str(row.get("cargo_file") or "").strip().upper() == "Y":
                        carrier.cargo_insurance_on_file = True
                    elif carrier.cargo_insurance_on_file is None:
                        carrier.cargo_insurance_on_file = False

                    if str(row.get("bond_file") or "").strip().upper() == "Y":
                        carrier.bond_on_file = True
                    elif carrier.bond_on_file is None:
                        carrier.bond_on_file = False

            policies: list[InsurancePolicy] = []
            for row in ins_rows:
                max_cov = _parse_int(row.get("max_cov_amount")) * 1000
                underl = _parse_int(row.get("underl_lim_amount")) * 1000
                policies.append(
                    InsurancePolicy(
                        docket_number=(str(row.get("docket_number")).strip() if row.get("docket_number") else None),
                        form_code=(str(row.get("ins_form_code")).strip() if row.get("ins_form_code") else None),
                        insurance_type=(str(row.get("mod_col_1")).strip() if row.get("mod_col_1") else None),
                        insurer_name=(str(row.get("name_company")).strip() if row.get("name_company") else None),
                        policy_number=(str(row.get("policy_no")).strip() if row.get("policy_no") else None),
                        max_coverage_usd=max_cov,
                        underlying_limit_usd=underl,
                        effective_date=(str(row.get("effective_date")).strip() if row.get("effective_date") else None),
                        cancel_effective_date=(
                            str(row.get("cancl_effective_date")).strip() if row.get("cancl_effective_date") else None
                        ),
                    )
                )
            carrier.active_insurers = policies
            evaluate_carrier_risk(carrier)


def build_mcp_summary(carriers: list[FmcsaCarrier], criteria: dict[str, Any]) -> dict[str, Any]:
    """Generate compact executive vetting and trucking lead summary for AI agents."""
    total = len(carriers)
    verdict_counts: dict[VettingVerdict, int] = {
        "PASS": 0,
        "CAUTION": 0,
        "HIGH_RISK": 0,
        "DO_NOT_USE": 0,
    }
    for c in carriers:
        verdict_counts[c.vetting_verdict] += 1

    if total == 0:
        overall_status = "NO_CARRIERS_FOUND"
    elif verdict_counts["DO_NOT_USE"] > 0:
        overall_status = "DO_NOT_USE_FLAGGED"
    elif verdict_counts["HIGH_RISK"] > 0:
        overall_status = "HIGH_RISK_FLAGGED"
    elif verdict_counts["CAUTION"] > 0:
        overall_status = "CAUTION_FLAGGED"
    else:
        overall_status = "ALL_VERIFIED_PASS"

    flagged = [
        {
            "dot_number": c.dot_number,
            "mc_number": c.mc_number,
            "legal_name": c.legal_name,
            "state": c.phy_state,
            "vetting_verdict": c.vetting_verdict,
            "risk_flags": c.risk_flags,
            "power_units": c.power_units,
            "bipd_on_file_usd": c.bipd_on_file_usd,
            "safer_url": c.safer_url,
        }
        for c in carriers
        if c.vetting_verdict != "PASS"
    ]

    return {
        "title": "FMCSA / USDOT Carrier Safety & Vetting Executive Summary",
        "overall_vetting_status": overall_status,
        "criteria": criteria,
        "metrics": {
            "total_carriers_analyzed": total,
            "verdict_breakdown": verdict_counts,
            "total_power_units": sum(c.power_units for c in carriers),
            "total_drivers": sum(c.total_drivers for c in carriers),
            "carriers_with_bipd_on_file": sum(1 for c in carriers if c.bipd_on_file_usd > 0),
            "hazmat_authorized_carriers": sum(1 for c in carriers if c.is_hazmat),
        },
        "flagged_carriers": flagged[:5],
    }

"""Official USITC Harmonized Tariff Schedule (HTS) REST API client and Landed Cost Engine."""

from __future__ import annotations

import asyncio
import re
import ssl
from typing import Any, Literal

import certifi
import httpx
from pydantic import BaseModel, Field

USITC_SEARCH_URL = "https://hts.usitc.gov/reststop/search"
USER_AGENT = "Mozilla/5.0 (compatible; USITCHtsTariffMCP/0.1; +https://apify.com)"

# CBP FY2026 Merchandise Processing Fee (MPF) & Harbor Maintenance Fee (HMF) constants
MPF_RATE = 0.003464
MPF_MIN_USD = 32.71
MPF_MAX_USD = 634.62
MPF_INFORMAL_USD = 2.62
MPF_FORMAL_THRESHOLD_USD = 2500.0
HMF_RATE = 0.00125

COLUMN_2_COUNTRIES = {"CU", "KP", "RU", "BY"}

# Active US Free Trade Agreements (SPI codes in USITC `special` field)
ORIGIN_TO_ACTIVE_FTA_SPIS: dict[str, tuple[str, ...]] = {
    "MX": ("S", "S+"),  # USMCA
    "CA": ("S", "S+"),  # USMCA
    "KR": ("KR",),      # KORUS FTA
    "AU": ("AU",),      # US-Australia FTA
    "SG": ("SG",),      # US-Singapore FTA
    "CL": ("CL",),      # US-Chile FTA
    "CO": ("CO",),      # US-Colombia TPA
    "IL": ("IL",),      # US-Israel FTA
    "JO": ("JO",),      # US-Jordan FTA
    "MA": ("MA",),      # US-Morocco FTA
    "OM": ("OM",),      # US-Oman FTA
    "PA": ("PA",),      # US-Panama TPA
    "PE": ("PE",),      # US-Peru PTPA
    "BH": ("BH",),      # US-Bahrain FTA
}

MPF_EXEMPT_ORIGINS = {"MX", "CA", "IL", "SG", "AU", "CL", "CO", "KR", "PA", "PE", "BH", "OM"}

_RATE_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_SPECIAL_FREE_RE = re.compile(r"Free\s*\(([^)]+)\)", re.IGNORECASE)
_SPECIAL_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*\(([^)]+)\)", re.IGNORECASE)


class HtsApiError(RuntimeError):
    """Raised when the official USITC HTS API returns an error or invalid payload."""


class CountryLandedCostBreakdown(BaseModel):
    """Landed cost calculation for a single origin country."""

    countryOfOrigin: str
    dutyProgramApplied: str
    ftaExempt: bool
    mpfExempt: bool
    baseDutyPercent: float
    baseDutyUsd: float
    additionalTariffPercent: float
    additionalTariffUsd: float
    chapter99ProgramNote: str
    mpfFeeUsd: float
    hmfFeeUsd: float
    totalDutiesAndFeesUsd: float
    effectiveDutyAndFeePercent: float
    totalLandedCostUsd: float
    hasSpecificRateComponent: bool


class Chapter99Reference(BaseModel):
    """Related Chapter 99 temporary tariff rule or suspension from USITC."""

    htsno: str
    description: str
    general: str | None = None
    special: str | None = None


class HtsTariffRecord(BaseModel):
    """Normalized USITC HTS record enriched with full landed cost & multi-country comparison."""

    htsno: str
    htsDigits: str
    indent: int
    description: str
    units: list[str] = Field(default_factory=list)
    generalRateText: str
    specialRateText: str
    otherRateText: str
    inheritedRateFromHtsNo: str | None = None
    activeFtaPrograms: list[str] = Field(default_factory=list)
    footnotes: list[str] = Field(default_factory=list)
    chapter99References: list[Chapter99Reference] = Field(default_factory=list)

    # Primary origin calculation fields (flattened for Apify dataset table views)
    countryOfOrigin: str
    shipmentValueUsd: float
    freightAndInsuranceUsd: float
    transportMode: Literal["ocean", "air", "truck"]
    dutyProgramApplied: str
    ftaExempt: bool
    mpfExempt: bool
    hasSpecificRateComponent: bool
    baseDutyPercent: float
    baseDutyUsd: float
    additionalTariffPercent: float
    additionalTariffUsd: float
    chapter99ProgramNote: str
    mpfFeeUsd: float
    hmfFeeUsd: float
    totalDutiesAndFeesUsd: float
    effectiveDutyAndFeePercent: float
    totalLandedCostUsd: float

    # Multi-country sourcing diversification comparison
    bestAlternativeCountry: str
    lowestLandedCostUsd: float
    maxSourcingSavingsUsd: float
    countryComparisons: list[CountryLandedCostBreakdown] = Field(default_factory=list)
    usitcSearchUrl: str


def normalize_hts_digits(hts_code: str | None) -> str:
    """Strip formatting dots/spaces from an HTS code string."""
    return re.sub(r"\D", "", hts_code or "")


def parse_ad_valorem_percent(rate_text: str | None) -> tuple[float, bool]:
    """Parse percentage duty rate and detect non-ad-valorem (specific/weight/unit) components."""
    cleaned = (rate_text or "").strip()
    if not cleaned or cleaned.lower() == "free":
        return 0.0, False

    has_specific = any(
        token in cleaned.lower()
        for token in ("¢", "/kg", "/g", "/l", "/doz", "/no", "/pr", "cents", "plus", "+")
    )
    match = _RATE_PERCENT_RE.search(cleaned)
    if match:
        return round(float(match.group(1)), 4), has_specific

    # Purely specific rate (e.g. "5¢/kg") has 0% ad-valorem component and flags specific fee
    return 0.0, True


def parse_special_programs(special_text: str | None) -> tuple[set[str], dict[str, float]]:
    """Extract duty-free and reduced-rate Special Program Indicator (SPI) codes."""
    text = (special_text or "").strip()
    free_spis: set[str] = set()
    reduced_spis: dict[str, float] = {}

    if not text:
        return free_spis, reduced_spis

    for match in _SPECIAL_FREE_RE.finditer(text):
        for token in match.group(1).split(","):
            code = token.strip().upper()
            if code:
                free_spis.add(code)

    for match in _SPECIAL_PCT_RE.finditer(text):
        pct = round(float(match.group(1)), 4)
        for token in match.group(2).split(","):
            code = token.strip().upper()
            if code and code not in free_spis:
                reduced_spis[code] = pct

    return free_spis, reduced_spis


def estimate_additional_tariff(
    htsno: str,
    origin: str,
    override_percent: float | None = None,
) -> tuple[float, str]:
    """Estimate Chapter 99 Section 301 (CN) and Section 232 (Steel/Aluminum) duties."""
    origin_code = origin.strip().upper()
    if override_percent is not None:
        return (
            round(float(override_percent), 4),
            f"User-supplied additional tariff override ({override_percent:.2f}%)",
        )

    digits = normalize_hts_digits(htsno)
    chapter = digits[:2]
    if digits.startswith(("98", "99")):
        return 0.0, "Chapter 98/99 special provision line"

    total_additional = 0.0
    notes: list[str] = []

    if origin_code == "CN":
        if digits.startswith("870380"):
            total_additional += 100.0
            notes.append("Section 301 (China): Electric vehicles (100%)")
        elif digits.startswith(("8541", "8542")):
            total_additional += 50.0
            notes.append("Section 301 (China): Solar cells/modules & semiconductors (50%)")
        elif chapter in {"72", "73", "84", "85", "94"}:
            total_additional += 25.0
            notes.append(
                "Section 301 (China): Batteries, machinery, electronics & furniture (25%)"
            )
        else:
            total_additional += 7.5
            notes.append("Section 301 (China List 4A): General consumer/industrial goods (7.5%)")

    if chapter in {"72", "73", "76"} and origin_code != "AU" and origin_code not in COLUMN_2_COUNTRIES:
        total_additional += 25.0
        notes.append("Section 232: Steel/Aluminum tariff (25%)")

    if not notes:
        return 0.0, "No Section 301 / Section 232 additional tariff estimated"

    return round(total_additional, 4), " + ".join(notes)


def calculate_landed_cost(
    *,
    htsno: str,
    general_text: str,
    special_text: str,
    other_text: str,
    origin: str,
    shipment_value_usd: float,
    freight_usd: float,
    transport_mode: Literal["ocean", "air", "truck"],
    override_additional_percent: float | None = None,
) -> CountryLandedCostBreakdown:
    """Compute base duty, Chapter 99 tariff, CBP MPF & HMF, and total landed cost in USD."""
    origin_code = origin.strip().upper()
    free_spis, reduced_spis = parse_special_programs(special_text)
    mfn_percent, mfn_specific = parse_ad_valorem_percent(general_text)

    fta_exempt = False
    mpf_exempt = False
    has_specific = mfn_specific
    base_duty_percent = mfn_percent
    duty_program = "General MFN (Column 1)" if mfn_percent > 0 or mfn_specific else "MFN Duty-Free"

    if origin_code in COLUMN_2_COUNTRIES:
        col2_pct, col2_specific = parse_ad_valorem_percent(other_text)
        if other_text.strip():
            base_duty_percent = col2_pct
            has_specific = col2_specific
            duty_program = f"Column 2 Rate ({origin_code})"
    else:
        eligible_spis = ORIGIN_TO_ACTIVE_FTA_SPIS.get(origin_code, ())
        matched_free = [spi for spi in eligible_spis if spi in free_spis]
        matched_reduced = [spi for spi in eligible_spis if spi in reduced_spis]

        if matched_free:
            fta_exempt = True
            has_specific = False
            base_duty_percent = 0.0
            duty_program = f"FTA Duty-Free (SPI {', '.join(matched_free)})"
        elif matched_reduced:
            fta_exempt = True
            base_duty_percent = min(reduced_spis[spi] for spi in matched_reduced)
            duty_program = f"FTA Preferential ({', '.join(matched_reduced)})"

        if fta_exempt and origin_code in MPF_EXEMPT_ORIGINS:
            mpf_exempt = True

    additional_pct, ch99_note = estimate_additional_tariff(
        htsno=htsno,
        origin=origin_code,
        override_percent=override_additional_percent,
    )

    base_duty_usd = round(shipment_value_usd * (base_duty_percent / 100.0), 2)
    additional_usd = round(shipment_value_usd * (additional_pct / 100.0), 2)

    if mpf_exempt:
        mpf_usd = 0.0
    elif shipment_value_usd < MPF_FORMAL_THRESHOLD_USD:
        mpf_usd = MPF_INFORMAL_USD
    else:
        mpf_usd = round(min(MPF_MAX_USD, max(MPF_MIN_USD, shipment_value_usd * MPF_RATE)), 2)

    hmf_usd = round(shipment_value_usd * HMF_RATE, 2) if transport_mode == "ocean" else 0.0

    total_duties_and_fees = round(base_duty_usd + additional_usd + mpf_usd + hmf_usd, 2)
    effective_pct = (
        round((total_duties_and_fees / shipment_value_usd) * 100.0, 2)
        if shipment_value_usd > 0
        else 0.0
    )
    total_landed = round(shipment_value_usd + freight_usd + total_duties_and_fees, 2)

    return CountryLandedCostBreakdown(
        countryOfOrigin=origin_code,
        dutyProgramApplied=duty_program,
        ftaExempt=fta_exempt,
        mpfExempt=mpf_exempt,
        baseDutyPercent=round(base_duty_percent, 4),
        baseDutyUsd=base_duty_usd,
        additionalTariffPercent=additional_pct,
        additionalTariffUsd=additional_usd,
        chapter99ProgramNote=ch99_note,
        mpfFeeUsd=mpf_usd,
        hmfFeeUsd=hmf_usd,
        totalDutiesAndFeesUsd=total_duties_and_fees,
        effectiveDutyAndFeePercent=effective_pct,
        totalLandedCostUsd=total_landed,
        hasSpecificRateComponent=has_specific,
    )


def _format_footnotes(footnotes: Any) -> list[str]:
    if not isinstance(footnotes, list):
        return []
    out: list[str] = []
    for item in footnotes:
        if isinstance(item, dict):
            val = str(item.get("value") or "").strip()
            if val and val not in out:
                out.append(val)
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


class HtsClient:
    """Async HTTP client wrapping the official USITC HTS REST API with rate inheritance."""

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
        self._prefix_cache: dict[str, list[dict[str, Any]]] = {}

    async def __aenter__(self) -> HtsClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTPX client."""
        await self._client.aclose()

    async def _fetch_search(self, keyword: str) -> list[dict[str, Any]]:
        """Call USITC reststop search endpoint with retries on transient errors."""
        key = keyword.strip()
        if key in self._prefix_cache:
            return self._prefix_cache[key]

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self._client.get(USITC_SEARCH_URL, params={"keyword": key})
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.8 * (2**attempt))
                    continue
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, list):
                    raise HtsApiError(
                        f"Unexpected USITC payload type ({type(payload).__name__}) for {key!r}"
                    )
                self._prefix_cache[key] = payload
                return payload
            except httpx.HTTPError as exc:
                last_err = exc
                if attempt < 2:
                    await asyncio.sleep(0.8 * (2**attempt))
                    continue

        raise HtsApiError(f"USITC request failed for keyword={key!r}: {last_err}") from last_err

    @staticmethod
    def _detect_hts_prefix(query: str) -> str | None:
        """Return normalized digit string if query looks like an HTS code."""
        cleaned = query.strip()
        if re.fullmatch(r"\d{4}(?:\.\d{2}){0,3}|\d{4,10}", cleaned):
            return normalize_hts_digits(cleaned)
        return None

    @staticmethod
    def _build_rate_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Index rate-bearing rows by normalized HTS digit code."""
        rate_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            htsno = str(row.get("htsno") or "").strip()
            digits = normalize_hts_digits(htsno)
            general = str(row.get("general") or "").strip()
            if digits and general:
                rate_map[digits] = row
        return rate_map

    @staticmethod
    def _resolve_rates(
        row: dict[str, Any],
        rate_map: dict[str, dict[str, Any]],
    ) -> tuple[str, str, str, str | None]:
        """Resolve general/special/other duty rates via longest ancestor HTS code."""
        htsno = str(row.get("htsno") or "").strip()
        digits = normalize_hts_digits(htsno)
        own_general = str(row.get("general") or "").strip()
        if own_general:
            return (
                own_general,
                str(row.get("special") or "").strip(),
                str(row.get("other") or "").strip(),
                None,
            )

        for prefix_len in (8, 6, 4):
            if len(digits) > prefix_len:
                candidate = rate_map.get(digits[:prefix_len])
                if candidate is not None:
                    return (
                        str(candidate.get("general") or "").strip(),
                        str(candidate.get("special") or "").strip(),
                        str(candidate.get("other") or "").strip(),
                        str(candidate.get("htsno") or "").strip() or None,
                    )

        return (
            str(row.get("general") or "").strip(),
            str(row.get("special") or "").strip(),
            str(row.get("other") or "").strip(),
            None,
        )

    async def search_and_calculate(
        self,
        *,
        query: str,
        country_of_origin: str = "CN",
        compare_countries: list[str] | None = None,
        shipment_value_usd: float = 25000.0,
        freight_and_insurance_usd: float = 1200.0,
        transport_mode: Literal["ocean", "air", "truck"] = "ocean",
        additional_tariff_percent: float | None = None,
        include_chapter99_notes: bool = True,
        max_results: int = 10,
    ) -> list[HtsTariffRecord]:
        """Search USITC HTS codes, inherit parent duty rates, and compute landed costs."""
        origin = country_of_origin.strip().upper()
        compare_list: list[str] = [origin]
        for code in compare_countries or ["CN", "VN", "MX", "KR"]:
            upper = code.strip().upper()
            if upper and upper not in compare_list:
                compare_list.append(upper)

        hts_digits_query = self._detect_hts_prefix(query)
        wants_ch99_directly = bool(hts_digits_query and hts_digits_query.startswith(("98", "99")))

        if hts_digits_query and len(hts_digits_query) >= 6:
            heading_6 = f"{hts_digits_query[:4]}.{hts_digits_query[4:6]}"
            raw_rows = await self._fetch_search(heading_6)
        else:
            raw_rows = await self._fetch_search(query)

        rate_tree_rows = list(raw_rows)
        chapter99_refs: list[Chapter99Reference] = []
        filtered_rows: list[dict[str, Any]] = []

        for row in raw_rows:
            htsno = str(row.get("htsno") or "").strip()
            if not htsno:
                continue
            digits = normalize_hts_digits(htsno)
            if not digits:
                continue

            is_ch98_99 = digits.startswith(("98", "99"))
            if is_ch98_99 and not wants_ch99_directly:
                if include_chapter99_notes:
                    chapter99_refs.append(
                        Chapter99Reference(
                            htsno=htsno,
                            description=str(row.get("description") or "").strip(),
                            general=str(row.get("general") or "").strip() or None,
                            special=str(row.get("special") or "").strip() or None,
                        )
                    )
                continue

            if hts_digits_query and not digits.startswith(hts_digits_query):
                continue

            filtered_rows.append(row)

        filtered_rows = filtered_rows[:max_results]
        rate_map = self._build_rate_map(rate_tree_rows)

        # For keyword queries, enrich up to 5 missing 6-digit parent headings automatically
        if not hts_digits_query:
            fetched_parents = 0
            for row in filtered_rows:
                htsno = str(row.get("htsno") or "").strip()
                digits = normalize_hts_digits(htsno)
                if str(row.get("general") or "").strip():
                    continue
                if len(digits) > 6 and fetched_parents < 5:
                    has_parent = any(digits[:plen] in rate_map for plen in (8, 6, 4) if len(digits) > plen)
                    if not has_parent:
                        parent_kw = f"{digits[:4]}.{digits[4:6]}"
                        parent_rows = await self._fetch_search(parent_kw)
                        rate_tree_rows.extend(parent_rows)
                        rate_map = self._build_rate_map(rate_tree_rows)
                        fetched_parents += 1

        records: list[HtsTariffRecord] = []
        for row in filtered_rows:
            htsno = str(row.get("htsno") or "").strip()
            digits = normalize_hts_digits(htsno)
            general_txt, special_txt, other_txt, inherited_from = self._resolve_rates(row, rate_map)
            free_spis, reduced_spis = parse_special_programs(special_txt)
            all_spis = sorted(free_spis | set(reduced_spis.keys()))

            primary = calculate_landed_cost(
                htsno=htsno,
                general_text=general_txt,
                special_text=special_txt,
                other_text=other_txt,
                origin=origin,
                shipment_value_usd=shipment_value_usd,
                freight_usd=freight_and_insurance_usd,
                transport_mode=transport_mode,
                override_additional_percent=additional_tariff_percent,
            )

            comparisons: list[CountryLandedCostBreakdown] = []
            for comp_origin in compare_list:
                if comp_origin == origin:
                    comparisons.append(primary)
                else:
                    comparisons.append(
                        calculate_landed_cost(
                            htsno=htsno,
                            general_text=general_txt,
                            special_text=special_txt,
                            other_text=other_txt,
                            origin=comp_origin,
                            shipment_value_usd=shipment_value_usd,
                            freight_usd=freight_and_insurance_usd,
                            transport_mode=transport_mode,
                            override_additional_percent=None,
                        )
                    )

            best_comp = min(comparisons, key=lambda c: c.totalLandedCostUsd)
            max_savings = round(primary.totalLandedCostUsd - best_comp.totalLandedCostUsd, 2)
            units_raw = row.get("units")
            units = [str(u) for u in units_raw] if isinstance(units_raw, list) else []

            try:
                indent_val = int(row.get("indent") or 0)
            except (TypeError, ValueError):
                indent_val = 0

            records.append(
                HtsTariffRecord(
                    htsno=htsno,
                    htsDigits=digits,
                    indent=indent_val,
                    description=str(row.get("description") or "").strip(),
                    units=units,
                    generalRateText=general_txt or "Inherited / Unspecified",
                    specialRateText=special_txt,
                    otherRateText=other_txt,
                    inheritedRateFromHtsNo=inherited_from,
                    activeFtaPrograms=all_spis,
                    footnotes=_format_footnotes(row.get("footnotes")),
                    chapter99References=chapter99_refs[:10],
                    countryOfOrigin=primary.countryOfOrigin,
                    shipmentValueUsd=round(shipment_value_usd, 2),
                    freightAndInsuranceUsd=round(freight_and_insurance_usd, 2),
                    transportMode=transport_mode,
                    dutyProgramApplied=primary.dutyProgramApplied,
                    ftaExempt=primary.ftaExempt,
                    mpfExempt=primary.mpfExempt,
                    hasSpecificRateComponent=primary.hasSpecificRateComponent,
                    baseDutyPercent=primary.baseDutyPercent,
                    baseDutyUsd=primary.baseDutyUsd,
                    additionalTariffPercent=primary.additionalTariffPercent,
                    additionalTariffUsd=primary.additionalTariffUsd,
                    chapter99ProgramNote=primary.chapter99ProgramNote,
                    mpfFeeUsd=primary.mpfFeeUsd,
                    hmfFeeUsd=primary.hmfFeeUsd,
                    totalDutiesAndFeesUsd=primary.totalDutiesAndFeesUsd,
                    effectiveDutyAndFeePercent=primary.effectiveDutyAndFeePercent,
                    totalLandedCostUsd=primary.totalLandedCostUsd,
                    bestAlternativeCountry=best_comp.countryOfOrigin,
                    lowestLandedCostUsd=best_comp.totalLandedCostUsd,
                    maxSourcingSavingsUsd=max(0.0, max_savings),
                    countryComparisons=comparisons,
                    usitcSearchUrl=f"https://hts.usitc.gov/?query={htsno}",
                )
            )

        return records


def build_mcp_summary(
    records: list[HtsTariffRecord],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Generate a compact, token-efficient MCP summary for AI supply-chain agents."""
    if not records:
        return {
            "title": "USITC HTS Tariff & Landed Cost MCP Summary",
            "status": "NO_MATCHING_HTS_RECORDS",
            "criteria": criteria,
            "recommendation": "Broaden query to a 6-digit HTS code (e.g. '8507.60') or shorter product keyword.",
            "items": [],
        }

    avg_effective_pct = round(
        sum(r.effectiveDutyAndFeePercent for r in records) / len(records),
        2,
    )
    highest_duty_line = max(records, key=lambda r: r.totalDutiesAndFeesUsd)
    fta_eligible_lines = sum(1 for r in records if r.ftaExempt)

    compact_items = [
        {
            "htsno": r.htsno,
            "description": r.description[:140],
            "general_mfn": r.generalRateText,
            "inherited_from": r.inheritedRateFromHtsNo,
            "origin": r.countryOfOrigin,
            "base_duty_pct": r.baseDutyPercent,
            "additional_ch99_pct": r.additionalTariffPercent,
            "effective_rate_pct": r.effectiveDutyAndFeePercent,
            "total_duties_fees_usd": r.totalDutiesAndFeesUsd,
            "total_landed_cost_usd": r.totalLandedCostUsd,
            "best_alternative_country": r.bestAlternativeCountry,
            "max_sourcing_savings_usd": r.maxSourcingSavingsUsd,
            "country_comparison_compact": [
                {
                    "country": c.countryOfOrigin,
                    "effective_pct": c.effectiveDutyAndFeePercent,
                    "duties_fees_usd": c.totalDutiesAndFeesUsd,
                    "landed_cost_usd": c.totalLandedCostUsd,
                }
                for c in r.countryComparisons
            ],
        }
        for r in records[:10]
    ]

    return {
        "title": "USITC HTS Tariff & Landed Cost MCP Summary",
        "status": "OK",
        "criteria": criteria,
        "metrics": {
            "total_hts_lines_evaluated": len(records),
            "avg_effective_duty_and_fee_percent": avg_effective_pct,
            "fta_exempt_lines_for_origin": fta_eligible_lines,
            "highest_duty_htsno": highest_duty_line.htsno,
            "highest_total_duties_and_fees_usd": highest_duty_line.totalDutiesAndFeesUsd,
            "chapter99_provisions_detected": len(records[0].chapter99References),
        },
        "items": compact_items,
    }

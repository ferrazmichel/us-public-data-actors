"""Official U.S. SEC EDGAR Submissions & XBRL CompanyFacts REST API client."""

from __future__ import annotations

import asyncio
import re
import ssl
from datetime import datetime
from typing import Any

import certifi
import httpx
from pydantic import BaseModel, Field

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# SEC EDGAR requires a descriptive User-Agent header with contact email
SEC_USER_AGENT = "FerrazDigitalAssets-SEC-MCP/0.1 (ferrazmichel@gmail.com)"

FAST_TICKER_MAP: dict[str, tuple[str, str]] = {
    "AAPL": ("0000320193", "Apple Inc."),
    "MSFT": ("0000789019", "MICROSOFT CORP"),
    "NVDA": ("0001045810", "NVIDIA CORP"),
    "GOOGL": ("0001652044", "Alphabet Inc."),
    "GOOG": ("0001652044", "Alphabet Inc."),
    "AMZN": ("0001018724", "AMAZON COM INC"),
    "META": ("0001326801", "Meta Platforms, Inc."),
    "TSLA": ("0001318605", "Tesla, Inc."),
    "BRK-B": ("0001067983", "BERKSHIRE HATHAWAY INC"),
    "JPM": ("0000019617", "JPMORGAN CHASE & CO"),
    "LLY": ("0000059478", "ELI LILLY & Co"),
    "V": ("0001403161", "VISA INC."),
    "WMT": ("0000104169", "Walmart Inc."),
}

SEC_8K_ITEM_DESCRIPTIONS: dict[str, str] = {
    "1.01": "Entry into Material Definitive Agreement",
    "1.02": "Termination of Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of Direct Financial Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Transfer Failure",
    "3.02": "Unregistered Sales of Equity Securities",
    "4.01": "Changes in Registrant Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.02": "Departure/Election of Directors or Principal Officers",
    "5.03": "Amendments to Articles/Bylaws or Fiscal Year Change",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)
NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss")
ASSETS_TAGS = ("Assets",)
EQUITY_TAGS = (
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
CASH_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)


class SecEdgarApiError(RuntimeError):
    """Raised when SEC EDGAR endpoints fail or reject requests."""


class FinancialSnapshot(BaseModel):
    """Audited US-GAAP annual snapshot extracted from XBRL CompanyFacts."""

    cik: str
    ticker: str | None = None
    companyName: str
    fiscalYearEndPeriod: str | None = None
    latestAnnualRevenueUsd: float | None = None
    latestAnnualNetIncomeUsd: float | None = None
    netProfitMarginPercent: float | None = None
    totalAssetsUsd: float | None = None
    stockholdersEquityUsd: float | None = None
    cashAndEquivalentsUsd: float | None = None


class SecFilingRecord(BaseModel):
    """Normalized SEC EDGAR filing enriched with archive links, 8-K items, and financials."""

    ticker: str
    companyName: str
    cik: str
    sic: str | None = None
    sicDescription: str | None = None
    form: str
    filingDate: str
    reportDate: str | None = None
    accessionNumber: str
    primaryDocument: str
    primaryDocDescription: str | None = None
    isInlineXbrl: bool = False
    items8KCoded: list[str] = Field(default_factory=list)
    items8KDecoded: str = ""
    documentUrl: str
    edgarFolderUrl: str
    fiscalYearEndPeriod: str | None = None
    latestAnnualRevenueUsd: float | None = None
    latestAnnualNetIncomeUsd: float | None = None
    netProfitMarginPercent: float | None = None
    totalAssetsUsd: float | None = None
    stockholdersEquityUsd: float | None = None
    cashAndEquivalentsUsd: float | None = None


def format_cik_10(raw_cik: str | int) -> str:
    """Zero-pad numeric CIK to SEC's 10-digit format."""
    digits = re.sub(r"\D", "", str(raw_cik))
    if not digits:
        raise ValueError(f"Invalid CIK value: {raw_cik!r}")
    return digits.zfill(10)


def decode_8k_items(raw_items: Any) -> tuple[list[str], str]:
    """Decode SEC Form 8-K item codes into human-readable descriptions."""
    codes: list[str] = []
    if isinstance(raw_items, list):
        codes = [str(c).strip() for c in raw_items if str(c).strip()]
    elif isinstance(raw_items, str) and raw_items.strip():
        codes = [c.strip() for c in raw_items.split(",") if c.strip()]

    decoded = [
        f"{code}: {SEC_8K_ITEM_DESCRIPTIONS[code]}"
        if code in SEC_8K_ITEM_DESCRIPTIONS
        else code
        for code in codes
    ]
    return codes, "; ".join(decoded)


def build_sec_document_urls(cik_10: str, accession_number: str, primary_document: str) -> tuple[str, str]:
    """Build direct SEC Archives document and folder URLs."""
    cik_int = str(int(cik_10))
    acc_clean = accession_number.replace("-", "").strip()
    doc_clean = primary_document.lstrip("/").strip()
    folder_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/"
    doc_url = f"{folder_url}{doc_clean}" if doc_clean else folder_url
    return doc_url, folder_url


def _extract_latest_annual_fact(
    us_gaap: dict[str, Any],
    tag_candidates: tuple[str, ...],
    *,
    is_duration: bool = False,
) -> tuple[float | None, str | None]:
    """Pick the most recent audited annual (10-K/20-F/40-F) USD fact across GAAP tag candidates."""
    candidates: list[tuple[str, str, int, float]] = []

    for tag_priority, tag_name in enumerate(tag_candidates):
        tag_obj = us_gaap.get(tag_name)
        if not isinstance(tag_obj, dict):
            continue
        usd_entries = tag_obj.get("units", {}).get("USD", [])
        if not isinstance(usd_entries, list):
            continue

        for entry in usd_entries:
            if not isinstance(entry, dict):
                continue
            form = str(entry.get("form") or "").upper()
            if form not in {"10-K", "10-K/A", "20-F", "40-F"}:
                continue

            end_str = str(entry.get("end") or "").strip()
            start_str = str(entry.get("start") or "").strip()
            val = entry.get("val")
            if not end_str or val is None:
                continue

            # For flow metrics (Revenue, Net Income), exclude single-quarter 90-day 10-K sub-rows
            if is_duration and start_str:
                try:
                    days = (
                        datetime.strptime(end_str, "%Y-%m-%d")
                        - datetime.strptime(start_str, "%Y-%m-%d")
                    ).days
                    if days < 300:
                        continue
                except ValueError:
                    pass

            filed_str = str(entry.get("filed") or "").strip()
            candidates.append((end_str, filed_str, -tag_priority, float(val)))

    if not candidates:
        return None, None

    best_end, _filed, _prio, best_val = max(candidates)
    return round(best_val, 2), best_end


def parse_xbrl_snapshot(
    companyfacts_payload: dict[str, Any],
    *,
    cik: str,
    ticker: str | None,
    company_name: str,
) -> FinancialSnapshot:
    """Extract audited 10-K GAAP financial snapshot from SEC CompanyFacts JSON."""
    us_gaap = companyfacts_payload.get("facts", {}).get("us-gaap", {})
    if not isinstance(us_gaap, dict):
        us_gaap = {}

    rev, rev_end = _extract_latest_annual_fact(us_gaap, REVENUE_TAGS, is_duration=True)
    net_inc, ni_end = _extract_latest_annual_fact(us_gaap, NET_INCOME_TAGS, is_duration=True)
    assets, assets_end = _extract_latest_annual_fact(us_gaap, ASSETS_TAGS, is_duration=False)
    equity, _ = _extract_latest_annual_fact(us_gaap, EQUITY_TAGS, is_duration=False)
    cash, _ = _extract_latest_annual_fact(us_gaap, CASH_TAGS, is_duration=False)

    margin: float | None = None
    if rev is not None and rev > 0 and net_inc is not None:
        margin = round((net_inc / rev) * 100.0, 2)

    return FinancialSnapshot(
        cik=cik,
        ticker=ticker,
        companyName=company_name,
        fiscalYearEndPeriod=rev_end or ni_end or assets_end,
        latestAnnualRevenueUsd=rev,
        latestAnnualNetIncomeUsd=net_inc,
        netProfitMarginPercent=margin,
        totalAssetsUsd=assets,
        stockholdersEquityUsd=equity,
        cashAndEquivalentsUsd=cash,
    )


class SecEdgarClient:
    """Async client for SEC EDGAR Submissions, Company Tickers, and XBRL CompanyFacts."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            verify=ssl_context,
            headers={
                "User-Agent": SEC_USER_AGENT,
                "Accept": "application/json",
            },
        )
        self._tickers_cache: dict[str, tuple[str, str]] | None = None
        self._semaphore = asyncio.Semaphore(4)

    async def __aenter__(self) -> SecEdgarClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTPX client."""
        await self._client.aclose()

    async def _get_json(self, url: str) -> dict[str, Any]:
        """Fetch JSON from SEC EDGAR respecting rate-limit pacing and retries."""
        last_err: Exception | None = None
        async with self._semaphore:
            for attempt in range(3):
                try:
                    resp = await self._client.get(url)
                    if resp.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        await asyncio.sleep(0.8 * (2**attempt))
                        continue
                    resp.raise_for_status()
                    payload = resp.json()
                    if not isinstance(payload, dict):
                        raise SecEdgarApiError(f"Expected dict JSON from {url}")
                    return payload
                except httpx.HTTPError as exc:
                    last_err = exc
                    if attempt < 2:
                        await asyncio.sleep(0.8 * (2**attempt))
                        continue

        raise SecEdgarApiError(f"SEC EDGAR request failed for {url}: {last_err}") from last_err

    async def _load_ticker_directory(self) -> dict[str, tuple[str, str]]:
        """Download and index SEC company_tickers.json."""
        if self._tickers_cache is not None:
            return self._tickers_cache

        raw = await self._get_json(SEC_TICKERS_URL)
        mapping: dict[str, tuple[str, str]] = {}
        for item in raw.values():
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").upper().strip()
            cik_str = item.get("cik_str")
            title = str(item.get("title") or "").strip()
            if ticker and cik_str is not None:
                mapping[ticker] = (format_cik_10(cik_str), title)

        self._tickers_cache = mapping
        return mapping

    async def resolve_entities(
        self,
        *,
        tickers_or_ciks: list[str] | None = None,
        company_name: str | None = None,
        max_name_matches: int = 3,
    ) -> list[tuple[str, str, str]]:
        """Resolve tickers, CIKs, or company name substrings to (cik_10, ticker, title)."""
        resolved: list[tuple[str, str, str]] = []
        seen_ciks: set[str] = set()
        needs_directory = bool(company_name and company_name.strip())

        for raw in tickers_or_ciks or []:
            token = raw.strip().upper()
            if not token:
                continue
            if re.fullmatch(r"(?:CIK)?\d{1,10}", token):
                cik_10 = format_cik_10(token)
                if cik_10 not in seen_ciks:
                    seen_ciks.add(cik_10)
                    resolved.append((cik_10, token, ""))
            elif token in FAST_TICKER_MAP:
                cik_10, title = FAST_TICKER_MAP[token]
                if cik_10 not in seen_ciks:
                    seen_ciks.add(cik_10)
                    resolved.append((cik_10, token, title))
            else:
                needs_directory = True

        if needs_directory:
            directory = await self._load_ticker_directory()
            for raw in tickers_or_ciks or []:
                token = raw.strip().upper()
                if not token or re.fullmatch(r"(?:CIK)?\d{1,10}", token) or token in FAST_TICKER_MAP:
                    continue
                hit = directory.get(token)
                if hit is not None:
                    cik_10, title = hit
                    if cik_10 not in seen_ciks:
                        seen_ciks.add(cik_10)
                        resolved.append((cik_10, token, title))

            if company_name and company_name.strip():
                needle = company_name.strip().lower()
                matches = 0
                for ticker, (cik_10, title) in directory.items():
                    if needle in title.lower():
                        if cik_10 not in seen_ciks:
                            seen_ciks.add(cik_10)
                            resolved.append((cik_10, ticker, title))
                            matches += 1
                            if matches >= max_name_matches:
                                break

        return resolved

    async def _fetch_company_data(
        self,
        *,
        cik_10: str,
        ticker_hint: str,
        forms_filter: set[str] | None,
        filing_date_from: str | None,
        include_financial_snapshot: bool,
        max_filings: int,
    ) -> tuple[list[SecFilingRecord], FinancialSnapshot | None]:
        sub_url = SEC_SUBMISSIONS_URL.format(cik=cik_10)
        if include_financial_snapshot:
            facts_url = SEC_FACTS_URL.format(cik=cik_10)
            submissions, facts = await asyncio.gather(
                self._get_json(sub_url),
                self._get_json(facts_url),
            )
        else:
            submissions = await self._get_json(sub_url)
            facts = None

        company_name = str(submissions.get("name") or "").strip() or ticker_hint
        tickers_list = submissions.get("tickers") or []
        resolved_ticker = (
            str(tickers_list[0]).upper()
            if isinstance(tickers_list, list) and tickers_list
            else ticker_hint
        )
        sic = str(submissions.get("sic") or "").strip() or None
        sic_desc = str(submissions.get("sicDescription") or "").strip() or None

        snapshot = (
            parse_xbrl_snapshot(
                facts,
                cik=cik_10,
                ticker=resolved_ticker,
                company_name=company_name,
            )
            if facts is not None
            else None
        )

        recent = submissions.get("filings", {}).get("recent", {})
        forms_col = recent.get("form") or []
        dates_col = recent.get("filingDate") or []
        report_dates_col = recent.get("reportDate") or []
        acc_col = recent.get("accessionNumber") or []
        doc_col = recent.get("primaryDocument") or []
        desc_col = recent.get("primaryDocDescription") or []
        items_col = recent.get("items") or []
        ixbrl_col = recent.get("isInlineXBRL") or []

        records: list[SecFilingRecord] = []
        row_count = min(len(forms_col), len(dates_col), len(acc_col), len(doc_col))

        for idx in range(row_count):
            form_val = str(forms_col[idx] or "").strip().upper()
            if forms_filter is not None and form_val not in forms_filter:
                continue

            filing_date = str(dates_col[idx] or "").strip()
            if filing_date_from and filing_date < filing_date_from:
                continue

            acc_no = str(acc_col[idx] or "").strip()
            primary_doc = str(doc_col[idx] or "").strip()
            doc_url, folder_url = build_sec_document_urls(cik_10, acc_no, primary_doc)

            raw_items = items_col[idx] if idx < len(items_col) else []
            coded_items, decoded_items = decode_8k_items(raw_items)
            report_date = (
                str(report_dates_col[idx] or "").strip() or None
                if idx < len(report_dates_col)
                else None
            )
            doc_desc = (
                str(desc_col[idx] or "").strip() or None
                if idx < len(desc_col)
                else None
            )
            is_ixbrl = bool(ixbrl_col[idx]) if idx < len(ixbrl_col) else False

            records.append(
                SecFilingRecord(
                    ticker=resolved_ticker,
                    companyName=company_name,
                    cik=cik_10,
                    sic=sic,
                    sicDescription=sic_desc,
                    form=form_val,
                    filingDate=filing_date,
                    reportDate=report_date,
                    accessionNumber=acc_no,
                    primaryDocument=primary_doc,
                    primaryDocDescription=doc_desc,
                    isInlineXbrl=is_ixbrl,
                    items8KCoded=coded_items,
                    items8KDecoded=decoded_items,
                    documentUrl=doc_url,
                    edgarFolderUrl=folder_url,
                    fiscalYearEndPeriod=snapshot.fiscalYearEndPeriod if snapshot else None,
                    latestAnnualRevenueUsd=snapshot.latestAnnualRevenueUsd if snapshot else None,
                    latestAnnualNetIncomeUsd=snapshot.latestAnnualNetIncomeUsd if snapshot else None,
                    netProfitMarginPercent=snapshot.netProfitMarginPercent if snapshot else None,
                    totalAssetsUsd=snapshot.totalAssetsUsd if snapshot else None,
                    stockholdersEquityUsd=snapshot.stockholdersEquityUsd if snapshot else None,
                    cashAndEquivalentsUsd=snapshot.cashAndEquivalentsUsd if snapshot else None,
                )
            )
            if len(records) >= max_filings:
                break

        return records, snapshot

    async def search_filings(
        self,
        *,
        tickers_or_ciks: list[str] | None = None,
        company_name: str | None = None,
        forms: list[str] | None = None,
        filing_date_from: str | None = None,
        include_financial_snapshot: bool = True,
        max_filings_per_company: int = 5,
    ) -> tuple[list[SecFilingRecord], list[FinancialSnapshot]]:
        """Resolve entities and fetch matching SEC filings + optional GAAP snapshots."""
        entities = await self.resolve_entities(
            tickers_or_ciks=tickers_or_ciks,
            company_name=company_name,
        )
        if not entities:
            return [], []

        normalized_forms = [f.strip().upper() for f in (forms or []) if f.strip()]
        forms_filter = None if (not normalized_forms or "ALL" in normalized_forms) else set(normalized_forms)

        results = await asyncio.gather(
            *(
                self._fetch_company_data(
                    cik_10=cik_10,
                    ticker_hint=ticker,
                    forms_filter=forms_filter,
                    filing_date_from=filing_date_from,
                    include_financial_snapshot=include_financial_snapshot,
                    max_filings=max_filings_per_company,
                )
                for cik_10, ticker, _title in entities
            )
        )

        all_records: list[SecFilingRecord] = []
        all_snapshots: list[FinancialSnapshot] = []
        for recs, snap in results:
            all_records.extend(recs)
            if snap is not None:
                all_snapshots.append(snap)

        all_records.sort(key=lambda r: r.filingDate, reverse=True)
        return all_records, all_snapshots


def build_mcp_summary(
    records: list[SecFilingRecord],
    snapshots: list[FinancialSnapshot],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Generate a compact, token-efficient MCP financial & SEC filings summary."""
    form_breakdown: dict[str, int] = {}
    for rec in records:
        form_breakdown[rec.form] = form_breakdown.get(rec.form, 0) + 1

    return {
        "title": "SEC EDGAR Filings & Audited GAAP Financials MCP Summary",
        "status": "OK" if (records or snapshots) else "NO_COMPANIES_MATCHED",
        "criteria": criteria,
        "metrics": {
            "companies_analyzed": len({s.cik for s in snapshots} or {r.cik for r in records}),
            "total_filings_returned": len(records),
            "form_breakdown": form_breakdown,
        },
        "financial_snapshots": [s.model_dump() for s in snapshots],
        "recent_filings": [
            {
                "ticker": r.ticker,
                "form": r.form,
                "filing_date": r.filingDate,
                "report_date": r.reportDate,
                "items_8k": r.items8KDecoded or None,
                "document_url": r.documentUrl,
            }
            for r in records[:20]
        ],
    }

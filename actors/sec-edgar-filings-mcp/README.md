# SEC EDGAR Filings, 8-K Events & XBRL Financials (MCP-Ready)

> Extract official U.S. SEC EDGAR filings (**10-K, 10-Q, 8-K, Form 4, DEF 14A, S-1**) and audited **US-GAAP XBRL financials** (`Revenue`, `Net Income`, `Net Margin %`, `Assets`, `Equity`, `Cash`) directly from `data.sec.gov`—compressing multi-megabyte SEC JSON feeds into clean, token-efficient datasets and MCP `OUTPUT` summaries.

---

## Use Cases

1. **AI Equity Research & Earnings Agents (MCP-Ready):** Pass stock tickers (`AAPL`, `NVDA`, `MSFT`) or CIKs to receive audited `10-K` GAAP financials alongside direct links to recent SEC filings without parsing 4 MB `companyfacts` XBRL blobs manually.
2. **Real-Time 8-K Material Event Decoding:** Automatically decodes cryptic Form 8-K item numbers (e.g. `2.02` Earnings Results, `1.05` Cybersecurity Incidents, `5.02` Executive Departures).
3. **Zero External API Keys Required:** Queries official SEC EDGAR APIs (`data.sec.gov` & `www.sec.gov`) with compliant `User-Agent` headers and built-in rate throttling.

---

## Input Parameters

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `tickersOrCiks` | Array | US stock tickers or 10-digit SEC CIKs | `["AAPL", "NVDA", "MSFT"]` |
| `companyName` | String | Optional company name search when ticker is unknown | `"Berkshire Hathaway"` |
| `forms` | Array | SEC form types (`"10-K"`, `"10-Q"`, `"8-K"`, `"4"`, `"ALL"`) | `["10-K", "10-Q", "8-K"]` |
| `filingDateFrom` | String | Earliest filing date (`YYYY-MM-DD`) | `"2026-01-01"` |
| `includeFinancialSnapshot` | Boolean | Enrich with audited 10-K XBRL financials | `true` |
| `maxFilingsPerCompany` | Integer | Max filings returned per company (1–100) | `5` |
| `outputMode` | String | `"detailed"` or `"mcp_summary"` | `"detailed"` |

---

## Connect via MCP (Claude Desktop, Cursor & AI Agents)

Connect this Actor directly via Apify's official MCP server (`https://mcp.apify.com`). Always prefer `outputMode: "mcp_summary"` inside interactive chat sessions for fast responses and minimal token usage.

### Remote HTTP (Recommended — OAuth)

```json
{
  "mcpServers": {
    "sec-edgar-filings": {
      "transport": "http",
      "url": "https://mcp.apify.com/?actors=ferraz_michel/sec-edgar-filings-mcp"
    }
  }
}
```

### Local `npx` (`@apify/actors-mcp-server`)

```json
{
  "mcpServers": {
    "sec-edgar-filings": {
      "command": "npx",
      "args": [
        "-y",
        "@apify/actors-mcp-server",
        "--actors",
        "ferraz_michel/sec-edgar-filings-mcp"
      ],
      "env": {
        "APIFY_TOKEN": "YOUR_APIFY_TOKEN"
      }
    }
  }
}
```

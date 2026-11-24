# USAspending Federal Contracts & Re-Compete Radar (MCP-Ready)

> Query official U.S. federal prime contracts and grants from **USAspending.gov** (`api.usaspending.gov/api/v2`) with zero external API keys—automatically enriching awards with **days until expiration** and **Re-Compete Radar** priority (`URGENT_RECOMPETE`, `UPCOMING_RECOMPETE`, `ACTIVE_LONG_TERM`) for GovCon teams and AI agents.

---

## Why Use This Actor?

1. **Built-In Re-Compete Radar:** Flags expiring federal contracts (`0–180 days` = `URGENT_RECOMPETE`, `181–365 days` = `UPCOMING_RECOMPETE`) so GovCon BD teams spot incumbent contracts ready for re-bid months before solicitation.
2. **Rich GovCon Filtering:** Filter by keywords, incumbent `recipientNames`, `naicsCodes`, `awardingAgency`, `placeOfPerformanceState`, `minAwardAmountUsd`, and `expiringWithinDays`.
3. **Zero API Keys Required:** Uses the official USAspending.gov REST API v2 with automatic pagination and direct `https://www.usaspending.gov/award/...` links.
4. **Token-Efficient MCP Summaries:** Choose `outputMode: "mcp_summary"` to get a compact `< 2 KB` digest with total contract volume, top incumbents, top agencies, and urgent re-compete alerts.

---

## Input Parameters

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `keywords` | Array | Search terms in award descriptions | `["cybersecurity"]` |
| `recipientNames` | Array | Filter by incumbent / contractor name | `["LOCKHEED MARTIN"]` |
| `naicsCodes` | Array | 2- to 6-digit NAICS industry codes | `["541512"]` |
| `awardingAgency` | String | Top-tier US federal agency name | `"Department of Defense"` |
| `placeOfPerformanceState` | String | Two-letter US state code | `"VA"` |
| `awardType` | String | `"contracts"`, `"grants"`, or `"all"` | `"contracts"` |
| `minAwardAmountUsd` | Number | Minimum award amount in USD | `1000000` |
| `startDateFrom` / `endDateTo` | String | Date window (`YYYY-MM-DD`) | `"2024-01-01"` / `"2027-12-31"` |
| `expiringWithinDays` | Integer | Filter & sort contracts expiring in `N` days | `180` |
| `maxRecords` | Integer | Maximum records returned (`1–200`) | `25` |
| `outputMode` | String | `"detailed"` or `"mcp_summary"` | `"detailed"` |

---

## Connect via MCP (Claude Desktop, Cursor & AI Agents)

Connect this Actor directly via Apify's official MCP server (`https://mcp.apify.com`). Always prefer `outputMode: "mcp_summary"` inside interactive chat sessions for fast responses and minimal token usage.

### Remote HTTP (Recommended — OAuth)

```json
{
  "mcpServers": {
    "usaspending-federal-contracts": {
      "transport": "http",
      "url": "https://mcp.apify.com/?actors=ferraz_michel/usaspending-federal-contracts-mcp"
    }
  }
}
```

### Local `npx` (`@apify/actors-mcp-server`)

```json
{
  "mcpServers": {
    "usaspending-federal-contracts": {
      "command": "npx",
      "args": [
        "-y",
        "@apify/actors-mcp-server",
        "--actors",
        "ferraz_michel/usaspending-federal-contracts-mcp"
      ],
      "env": {
        "APIFY_TOKEN": "YOUR_APIFY_TOKEN"
      }
    }
  }
}
```

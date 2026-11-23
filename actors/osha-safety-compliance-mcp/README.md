# OSHA Safety & Compliance Search (MCP-Ready)

Query official **US Department of Labor (DOL) OSHA** workplace safety inspections, citations, violations, and penalty amounts through an **API-first, token-efficient Apify Actor** built for **B2B due diligence, insurance underwriting, legal research, and AI agents (MCP)**.

---

## Why Use This Actor Instead of Manual Portals or Fragile Scrapers?

- **Official US Government Open Data API:** Queries the DOL Open Data API directly over HTTPS — zero headless browser overhead, zero proxy blocks, and clean structured fields.
- **Automatic Pagination Past the 200-Row Limit:** The native DOL endpoint caps responses at 200 records per request. This Actor automatically paginates up to your configured `maxRecords`.
- **Automatic Inspection + Violation Join:** Optionally fetches linked violations by `activity_nr` and calculates `violation_count`, `total_initial_penalty`, and `total_current_penalty` per establishment.
- **Built for AI Agents (MCP Summary Mode):** Select `outputMode: "mcp_summary"` to get a compact JSON digest in `OUTPUT` summarizing total penalties, violation severity breakdown (`Serious`, `Willful`, `Repeat`), and top cited OSHA standards without overflowing your LLM context window.

---

## Common Use Cases

1. **Vendor & Contractor Risk Vetting (AI Agents):** Let an AI compliance agent check a supplier's last 5 years of OSHA safety citations before onboarding.
2. **Insurance & Legal Due Diligence:** Pull inspection histories and penalty trends across a company name or NAICS industry code in a specific US state.
3. **B2B Safety & Compliance Sales:** Identify high-hazard facilities or industries (`naicsCode` + `state`) with recent citations for safety training, PPE, or EHS software outreach.

---

## Input Example

```json
{
  "establishmentName": "Amazon",
  "state": "TX",
  "includeViolations": true,
  "maxRecords": 50,
  "outputMode": "mcp_summary"
}
```

### Input Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| `establishmentName` | `string` | Company or establishment name filter (partial match) |
| `state` | `string` | Two-letter US state code (e.g., `TX`, `CA`, `OH`) |
| `naicsCode` | `string` | 2- to 6-digit NAICS industry code prefix |
| `openDateFrom` / `openDateTo` | `string` | Inspection open date bounds (`YYYY-MM-DD`) |
| `includeViolations` | `boolean` | Fetch and sum linked OSHA violations & penalties (default `true`) |
| `maxRecords` | `integer` | Maximum inspections to return (`1` to `1000`, default `50`) |
| `outputMode` | `string` | `detailed` (full dataset rows) or `mcp_summary` (adds compact risk digest to `OUTPUT`) |
| `dolApiKey` | `string` | Optional DOL Open Data API key override |

---

## Output Example (`OUTPUT` in `mcp_summary` Mode)

```json
{
  "query": {
    "establishmentName": "Amazon",
    "state": "TX",
    "naicsCode": null,
    "openDateFrom": null,
    "openDateTo": null,
    "includeViolations": true
  },
  "metrics": {
    "inspections_returned": 12,
    "total_violations": 19,
    "total_initial_penalty_usd": 148250.0,
    "total_current_penalty_usd": 94100.0,
    "violation_types": {
      "S": 14,
      "O": 5
    },
    "top_cited_standards": [
      { "standard": "19100178", "count": 4 },
      { "standard": "19100022", "count": 3 }
    ],
    "states_breakdown": {
      "TX": 12
    }
  },
  "inspections_digest": [
    {
      "activity_nr": "1701234",
      "estab_name": "Amazon.com Services LLC",
      "city_state": "Houston, TX",
      "open_date": "2025-08-14",
      "insp_type": "C",
      "naics_code": "493110",
      "violation_count": 2,
      "current_penalty_usd": 16131.0
    }
  ]
}
```

---

## Using with AI Agents via Apify MCP

Connect this Actor directly to **Claude Desktop, Cursor, LangGraph, or CrewAI** via Apify's official MCP server (`https://mcp.apify.com`) using OAuth or your Apify token. Always prefer `outputMode: "mcp_summary"` inside interactive chat sessions for fast responses and minimal token usage.

### Remote HTTP (Recommended — OAuth)

```json
{
  "mcpServers": {
    "osha-safety-compliance": {
      "transport": "http",
      "url": "https://mcp.apify.com/?actors=ferraz_michel/osha-safety-compliance-mcp"
    }
  }
}
```

### Local `npx` (`@apify/actors-mcp-server`)

```json
{
  "mcpServers": {
    "osha-safety-compliance": {
      "command": "npx",
      "args": [
        "-y",
        "@apify/actors-mcp-server",
        "--actors",
        "ferraz_michel/osha-safety-compliance-mcp"
      ],
      "env": {
        "APIFY_TOKEN": "YOUR_APIFY_TOKEN"
      }
    }
  }
}
```

# EPA ECHO Environmental Compliance & Facility Search (MCP-Ready)

> Search official US EPA regulated facilities for Clean Air Act (CAA), Clean Water Act (CWA), and RCRA hazardous waste compliance status, significant non-compliance (SNC), formal enforcement actions, and penalty totals via API.

---

## Features

- **Official EPA Data:** Directly queries the live U.S. Environmental Protection Agency (EPA) ECHO REST Services.
- **Zero API Key Requirement:** Free and open government data without registration or token limits.
- **2-Step Orchestration Solved:** Automatically negotiates EPA's `get_facilities` QueryID setup, pagination (`get_qid`), and response hydration.
- **MCP-Ready (Model Context Protocol):** Outputs a structured `mcp_summary` in the `OUTPUT` key-value store, enabling AI agents (Claude Desktop, Cursor, Zapier) to assess corporate environmental risk without token bloat.
- **Multi-Program Coverage:** Identifies active permits and violations across Clean Air Act, Clean Water Act, Safe Drinking Water Act, and RCRA Waste.

---

## Input Parameters

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `facilityName` | String | Facility or operating company name | `"Tesla"`, `"Amazon"`, `"Chevron"` |
| `state` | String | Two-letter US state abbreviation | `"TX"`, `"CA"`, `"OH"` |
| `city` | String | City where the facility is located | `"Austin"`, `"Houston"` |
| `zipCode` | String | 5-digit US ZIP Code | `"78725"` |
| `naicsCode` | String | NAICS industry classification code | `"336111"` |
| `significantNonComplianceOnly` | Boolean | Filter strictly for Significant Non-Compliance | `false` |
| `maxRecords` | Integer | Maximum records returned (1–200) | `50` |
| `outputMode` | String | Output mode (`"detailed"` or `"mcp_summary"`) | `"detailed"` |

---

## MCP Executive Summary Output Example

```json
{
  "title": "EPA ECHO Environmental Risk Assessment (Executive Summary)",
  "risk_level": "CRITICAL",
  "criteria": {
    "facility_name": "Tesla",
    "state": "TX"
  },
  "metrics": {
    "total_facilities_analyzed": 38,
    "facilities_with_significant_non_compliance": 1,
    "facilities_with_active_violations": 2,
    "total_formal_enforcement_actions": 0,
    "total_penalties_assessed_usd": 0.0,
    "environmental_statutes_coverage": {
      "CAA (Air)": 1,
      "CWA (Water)": 28,
      "RCRA (Waste)": 8,
      "SDWA (Drinking Water)": 0
    }
  },
  "flagged_high_risk_facilities": [
    {
      "facility_name": "TESLA GIGAFACTORY TEXAS",
      "city": "AUSTIN",
      "state": "TX",
      "has_snc": true,
      "compliance_status": "Significant Violation",
      "total_penalties_usd": 0.0,
      "echo_report_url": "https://echo.epa.gov/detailed-facility-report?fid=110071338212"
    }
  ]
}
```

---

## Local Development & Testing

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest pytest-asyncio
pytest tests/
```


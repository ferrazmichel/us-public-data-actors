# FMCSA & USDOT Carrier Safety, Authority & Leads (MCP-Ready)

> Vet US motor carriers and extract active trucking leads using official USDOT / FMCSA open datasets—combining Company Census profiles, MC/MX operating authority, BIPD insurance coverage, and a structured MCP risk verdict (`PASS`, `CAUTION`, `HIGH_RISK`, `DO_NOT_USE`).

---

## Use Cases

1. **Automated Carrier Vetting (Freight Brokers, Shippers & AI Agents):**
   - Look up any carrier by `dotNumber`, `mcNumber`, or `carrierName`.
   - Instantly verify active USDOT status, operating authority (`Common`, `Contract`, `Broker`), pending revocations, BIPD insurance on file, safety rating (`Satisfactory` / `Conditional` / `Unsatisfactory`), and new-authority risk (< 90 days old).
2. **New Carrier & Fleet Lead Generation (Insurance Agents, Factoring & B2B Sales):**
   - Query active carriers by `state`, `city`, `addedAfterDate`, `minPowerUnits`, and `hazmatOnly`.
   - Extract company officers, phone numbers, email addresses, fleet sizes (`power_units`, `total_drivers`), and carried cargo types (`General Freight`, `Refrigerated Food`, `HazMat`, etc.).
3. **Zero External API Key Required:**
   - Queries official U.S. Department of Transportation Socrata APIs (`data.transportation.gov`) directly without any user setup.

---

## Input Parameters

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `dotNumber` | String | Official USDOT number | `"22105"` |
| `mcNumber` | String | Motor Carrier docket number | `"202830"` or `"MC-202830"` |
| `carrierName` | String | Legal or DBA company name | `"J B Hunt"` |
| `state` | String | Two-letter US physical state code | `"TX"`, `"CA"`, `"IL"` |
| `city` | String | Physical city name | `"HOUSTON"` |
| `statusCode` | String | USDOT status (`"A"`, `"I"`, `"ALL"`) | `"A"` |
| `addedAfterDate` | String | Filter newly added carriers (`YYYY-MM-DD`) | `"2026-11-01"` |
| `minPowerUnits` | Integer | Minimum truck/power unit fleet size | `5` |
| `hazmatOnly` | Boolean | Hazardous materials carriers only | `false` |
| `includeAuthorityAndInsurance` | Boolean | Join FMCSA L&I authority & policy data | `true` |
| `maxRecords` | Integer | Maximum carriers returned (1–200) | `20` |
| `outputMode` | String | `"detailed"` or `"mcp_summary"` | `"detailed"` |

---

## MCP Executive Vetting Summary Example (`OUTPUT`)

```json
{
  "title": "FMCSA / USDOT Carrier Safety & Vetting Executive Summary",
  "overall_vetting_status": "CAUTION_FLAGGED",
  "criteria": {
    "state": "TX",
    "status_code": "A"
  },
  "metrics": {
    "total_carriers_analyzed": 10,
    "verdict_breakdown": {
      "PASS": 7,
      "CAUTION": 3,
      "HIGH_RISK": 0,
      "DO_NOT_USE": 0
    },
    "total_power_units": 84,
    "total_drivers": 92,
    "carriers_with_bipd_on_file": 6,
    "hazmat_authorized_carriers": 1
  },
  "flagged_carriers": []
}
```

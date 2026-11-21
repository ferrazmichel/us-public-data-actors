# FDA Drug, Medical Device & Food Recall Radar (MCP-Ready)

> Real-time U.S. FDA enforcement recall intelligence across **Drugs, Medical Devices, and Food** via official openFDA APIs—combining multi-domain querying, clean ISO date normalization, hazard risk scoring (`CRITICAL`, `HIGH`, `MODERATE`, `LOW`), and compact MCP summaries for healthcare, legal, and supply-chain AI agents.

---

## Use Cases

1. **Hospital & Pharmacy Recall Monitoring:** Track `Ongoing` `Class I` drug and medical device recalls across manufacturers (`Medtronic`, `Abbott`, `Pfizer`) or specific products (`catheter`, `pacemaker`, `insulin`).
2. **Product Liability & Compliance Due Diligence:** Search FDA enforcement history across all 3 domains simultaneously (`domain: "all"`), automatically handling openFDA Lucene query formatting and empty-result 404 responses.
3. **Supply-Chain & AI Agent Alerts (MCP-Ready):** Consume clean ISO `YYYY-MM-DD` dates, extracted `openfda` metadata (`brandNames`, `deviceNames`, `productNdcs`), and pre-computed `riskLevel` alerts via Key-Value Store `OUTPUT`.

---

## Input Parameters

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `domain` | String | FDA domain (`"all"`, `"device"`, `"drug"`, `"food"`) | `"all"` |
| `searchQuery` | String | Keyword across product, reason, brand, or device name | `"catheter"` |
| `recallingFirm` | String | Recalling manufacturer or distributor name | `"Medtronic"` |
| `classification` | String | Hazard severity (`"Class I"`, `"Class II"`, `"Class III"`, `"ALL"`) | `"Class I"` |
| `status` | String | Recall status (`"Ongoing"`, `"Terminated"`, `"Completed"`, `"ALL"`) | `"Ongoing"` |
| `state` | String | Two-letter US state of the recalling firm | `"CA"` |
| `reportDateFrom` | String | Minimum FDA report date (`YYYY-MM-DD`) | `"2026-01-01"` |
| `maxRecords` | Integer | Maximum merged recall records (1–200) | `15` |
| `outputMode` | String | `"detailed"` or `"mcp_summary"` | `"detailed"` |

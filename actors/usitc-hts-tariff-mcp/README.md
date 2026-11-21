# US Tariff, HTS Code & Landed Cost Calculator (MCP-Ready)

> Look up official U.S. International Trade Commission (USITC) Harmonized Tariff Schedule (HTS) duty rates and compute complete US import landed costs—combining automatic 10-digit rate inheritance, USMCA/FTA exemptions, Chapter 99 Section 301/232 estimates, CBP MPF & HMF import fees, and multi-country sourcing comparisons (`China vs. Vietnam vs. Mexico vs. South Korea`).

---

## Why This Actor Beats Raw USITC API Lookups

1. **Solves 10-Digit HTS Rate Inheritance Automatically:** In the raw USITC API, 10-digit statistical codes (e.g. `8507.60.00.10`) return blank `general` / `special` / `other` strings because tariff rates sit on the 8-digit parent (`8507.60.00`). This Actor fetches the heading tree automatically and attaches inherited rates + related Chapter 99 (`9902.*` / `9903.*`) provisions.
2. **Full CBP Customs Fee Engine (MPF + HMF + FTA):** Computes FY2026 **Merchandise Processing Fee (MPF: 0.3464%, min \$32.71 / max \$634.62 formal or \$2.62 informal, \$0 FTA-exempt)** and **Harbor Maintenance Fee (HMF: 0.125% ocean)**.
3. **Instant Multi-Country Sourcing Comparison:** Evaluates your `countryOfOrigin` side-by-side against `compareCountries` (default `CN`, `VN`, `MX`, `KR`), surfacing `bestAlternativeCountry` and `maxSourcingSavingsUsd` in both dataset rows and the compact MCP `OUTPUT` summary.
4. **Zero API Keys Required:** Queries official `https://hts.usitc.gov/reststop/search` directly with no external tokens.

---

## Input Parameters

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `query` | String | 6/8/10-digit HTS code or product keyword | `"8507.60"`, `"8507.60.00.10"`, `"solar panels"` |
| `countryOfOrigin` | String | Primary 2-letter ISO country of origin | `"CN"` |
| `compareCountries` | Array | Alternative origins for sourcing cost comparison | `["CN", "VN", "MX", "KR"]` |
| `shipmentValueUsd` | Number | Commercial invoice FOB customs value (USD) | `25000` |
| `freightAndInsuranceUsd` | Number | International freight & insurance cost (USD) | `1200` |
| `transportMode` | String | Arrival mode (`"ocean"`, `"air"`, `"truck"`) | `"ocean"` |
| `additionalTariffPercent` | Number | Optional Chapter 99 / Section 301 / 232 override % | `25` |
| `includeChapter99Notes` | Boolean | Attach related Chapter 99 provisions returned by USITC | `true` |
| `maxResults` | Integer | Maximum HTS lines to analyze (1–100) | `10` |
| `outputMode` | String | `"detailed"` or `"mcp_summary"` | `"detailed"` |

---

## MCP Executive Tariff Summary Example (`OUTPUT`)

```json
{
  "title": "USITC HTS Tariff & Landed Cost MCP Summary",
  "status": "OK",
  "metrics": {
    "total_hts_lines_evaluated": 4,
    "avg_effective_duty_and_fee_percent": 28.87,
    "fta_exempt_lines_for_origin": 0,
    "highest_duty_htsno": "8507.60.00.10",
    "highest_total_duties_and_fees_usd": 7217.85
  },
  "items": [
    {
      "htsno": "8507.60.00.10",
      "general_mfn": "3.4%",
      "origin": "CN",
      "effective_rate_pct": 28.87,
      "total_landed_cost_usd": 33417.85,
      "best_alternative_country": "MX",
      "max_sourcing_savings_usd": 7186.6
    }
  ]
}
```

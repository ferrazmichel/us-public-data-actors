# US 1099-NEC \$2,000 Threshold, State Rules & Backup Withholding (MCP-Ready)

> Audit 2026 US Form 1099-NEC compliance across **all 50 US states + Washington, D.C.**—identifying the high-risk **\$600–\$1,999 Federal-vs-State Filing Trap**, IRS CF/SF vs. direct state e-filing portals, IRC § 6050W (`1099-K`) & corporate/attorney exemptions, and **24% mandatory backup withholding** when Form W-9 is missing.

---

## Why US Businesses & Accounting AI Agents Need This in 2026

1. **The 2026 Federal (\$2,000) vs. State (\$600) Filing Trap:** While the federal Form 1099-NEC threshold increased from **\$600 to \$2,000** for 2026, ~20 states (including **California, Pennsylvania, Massachusetts, New Jersey (\$1,000), Missouri (\$1,200), Oregon, Wisconsin, Connecticut**) keep independent lower thresholds. Worse: **IRS Combined Federal/State Filing (CF/SF) does not transmit state records when no federal Form 1099-NEC is filed**—forcing direct state portal uploads (`myPATH`, `iWire`, `MassTaxConnect`, etc.).
2. **24% Backup Withholding Trap (IRC § 3406):** Paying even **\$0.01** without a verified W-9/TIN triggers 24% federal backup withholding (+ up to 5%–8% state withholding) and **eliminates all \$2,000 / \$600 exemptions**.
3. **Corporate vs. Attorney & 1099-K Rules:** Automatically enforces IRC § 6050W credit-card exclusions and the legal-services exception (`isAttorneyOrLegalServices`) for C-Corps/S-Corps.
4. **Two Operating Modes:**
   - **51-State Matrix Mode (`states: ["ALL"]`):** Evaluate a scenario across all 50 states + D.C. at once.
   - **CPA/ERP Vendor Batch Audit (`contractors: [...]`):** Pass an array of vendors for instant compliance verdicts, withholding totals, and IRS IRC § 6721 penalty exposure.

---

## Input Parameters

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `states` | Array | State codes or `["ALL"]` for 51 jurisdictions | `["CA", "NY", "TX", "PA", "MA"]` |
| `taxYear` | Integer | Tax year (`2026` = \$2,000 Fed; `2025` = \$600 Fed) | `2026` |
| `paymentAmountUsd` | Number | Annual contractor payments in USD | `1250` |
| `entityType` | String | W-9 payee classification | `"individual_sole_prop"` |
| `paymentMethod` | String | `"ach_wire_check_cash"` or `"credit_card_1099k"` | `"ach_wire_check_cash"` |
| `w9Verified` | Boolean | Valid signed Form W-9 / TIN on file | `true` |
| `isAttorneyOrLegalServices` | Boolean | Override C/S-Corp exemption for legal fees | `false` |
| `contractors` | Array | Optional batch list of vendor records | `[{name, state, paymentAmountUsd, ...}]` |
| `outputMode` | String | `"detailed"` or `"mcp_summary"` | `"detailed"` |

---

## Connect via MCP (Claude Desktop, Cursor & AI Agents)

Connect this Actor directly via Apify's official MCP server (`https://mcp.apify.com`). Always prefer `outputMode: "mcp_summary"` inside interactive chat sessions for fast responses and minimal token usage.

### Remote HTTP (Recommended — OAuth)

```json
{
  "mcpServers": {
    "us-1099-nec-compliance": {
      "transport": "http",
      "url": "https://mcp.apify.com/?actors=ferraz_michel/us-1099-nec-state-compliance-mcp"
    }
  }
}
```

### Local `npx` (`@apify/actors-mcp-server`)

```json
{
  "mcpServers": {
    "us-1099-nec-compliance": {
      "command": "npx",
      "args": [
        "-y",
        "@apify/actors-mcp-server",
        "--actors",
        "ferraz_michel/us-1099-nec-state-compliance-mcp"
      ],
      "env": {
        "APIFY_TOKEN": "YOUR_APIFY_TOKEN"
      }
    }
  }
}
```

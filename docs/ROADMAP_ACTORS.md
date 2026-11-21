# Roadmap Técnico dos Actors (Onda 1 a Onda 2)

> Especificação objetiva dos 3 primeiros Actors prioritários e backlog futuro do portfólio.

---

## Actor #1 (MVP em Construção) — `osha-safety-compliance-mcp`

- **Fonte oficial:** U.S. Department of Labor (DOL) Open Data API v4 (`https://apiprod.dol.gov/v4/get/`), requer query parameter `X-API-KEY` gratuito do portal da DOL.
- **Dor que resolve:** Consultar inspeções, violações e multas de segurança do trabalho (OSHA) por empresa, estado, código NAICS e intervalo de datas sem precisar lidar com paginação manual (teto da API é de **200 registros por chamada**) nem cruzar manualmente `inspection` e `violation` por `activity_nr`.
- **Diferencial MCP:** Modo `mcp_summary` entrega total de inspeções, número de violações (Serious / Willful / Repeat), soma de multas iniciais vs. atuais e top padrões OSHA citados — em poucos KB de JSON.
- **Diretório:** [`actors/osha-safety-compliance-mcp`](../actors/osha-safety-compliance-mcp).

---

## Actor #2 — `epa-echo-environmental-mcp`

- **Fonte oficial:** U.S. EPA ECHO (Enforcement and Compliance History Online) REST Services — serviços públicos gratuitos para busca de instalações reguladas (Clean Air Act, Clean Water Act, RCRA).
- **Dor que resolve:** A API da EPA exige orquestração em 2 etapas (`get_facilities` gerando um `QueryID` + `get_qid` paginando os resultados) e chamadas separadas para Detailed Facility Reports (DFR). Equipes de ESG, consultorias ambientais e agentes de IA preferem uma única chamada limpa.
- **Entregáveis planejados:**
  - Busca por empresa, cidade, estado, CEP (ZIP), NAICS ou status de infração significativa (`SNC`).
  - Modo `mcp_summary` com flag de violação ativa nos últimos 12 trimestres, total de multas aplicadas e principais programas ambientais envolvidos.

---

## Actor #3 — `fmcsa-carrier-safety-mcp`

- **Fonte oficial:** USDOT / FMCSA Socrata/Open Data (`data.transportation.gov`) + endpoints públicos SAFER/QCMobile (quando aplicável com API Key gratuita FMCSA).
- **Dor que resolve:** Corretoras de frete, seguradoras de carga, empresas de factoring e compradores B2B nos EUA precisam validar rapidamente se uma transportadora (por USDOT, MC ou estado) está autorizada, possui seguro ativo, quantos caminhões/motoristas opera e qual seu histórico de inspeções (*Out-of-Service rate*).
- **Entregáveis planejados:**
  - Modo 1: *Single Carrier Vetting* (rápido para MCP — retorna perfil completo de risco da transportadora).
  - Modo 2: *New/Filtered Carrier Leads* (por estado, tamanho da frota e data recente de cadastro para equipes comerciais).

---

## Actor #4 (Projeto #3) — `usitc-hts-tariff-mcp`

- **Fonte oficial:** U.S. International Trade Commission (USITC) Harmonized Tariff Schedule REST API (`https://hts.usitc.gov/reststop/search`), gratuita e sem autenticação.
- **Dor que resolve:** A API oficial retorna campos de tarifa vazios nos códigos estatísticos de 10 dígitos (`8507.60.00.10`), não calcula automaticamente isenções de Acordos de Livre Comércio (USMCA `MX`/`CA`, KORUS `KR`, etc.), nem soma tarifas adicionais do Capítulo 99 (Section 301/232) ou taxas alfandegárias CBP (**MPF** `0,3464%` e **HMF** `0,125%`).
- **Diferencial MCP & E-commerce:** Herda tarifas da hierarquia pai automaticamente, calcula **Landed Cost** completo em USD e compara múltiplos países de origem lado a lado (`CN` vs. `VN` vs. `MX` vs. `KR`) para agentes de compras, Shopify/Amazon FBA e despachantes.
- **Diretório:** [`actors/usitc-hts-tariff-mcp`](../actors/usitc-hts-tariff-mcp).

---

## Actor #5 — `us-1099-nec-state-compliance-mcp`

- **Base normativa:** IRS Form 1099-NEC 2026 (teto federal de \$2.000), IRC §§ 6041A / 6050W / 3406 / 6721 e regras individuais dos **50 estados + D.C.**
- **Dor que resolve:** Em 2026 o teto federal subiu de \$600 para **\$2.000**, mas ~20 estados mantiveram tetos estaduais menores (\$600 / \$1.000 / \$1.200) — e o IRS CF/SF não transmite para o estado quando não há envio federal. Além disso, falta de W-9 dispara **24% de backup withholding** desde \$0,01.
- **Modos de operação:** Matriz dos 51 estados/DC (`states: ["ALL"]`) e auditoria em lote de fornecedores (`contractors: [...]`) para CPAs, ERPs e agentes contábeis.
- **Diretório:** [`actors/us-1099-nec-state-compliance-mcp`](../actors/us-1099-nec-state-compliance-mcp).

---

## Backlog Futuro (Onda 2 — após os 3 primeiros estarem no ar)

| Slug Sugerido | Fonte Oficial | Diferencial |
| :--- | :--- | :--- |
| `openfda-recall-device-radar` | openFDA API (Drugs, Food, MAUDE Devices) | Alertas estruturados de recalls e eventos adversos para farma/jurídico/IA |
| `sec-edgar-filings-mcp` | SEC EDGAR Submissions & Company Facts JSON API | Extração limpa de 10-K/8-K/Form 4 sem rate-limit acidental (User-Agent compliance) |
| `samgov-opportunities-mcp` | SAM.gov Public API | Busca enxuta por NAICS + resumo token-friendly de prazos/contatos de RFPs |

---

## Tabela de Atividades

| Marco | Actor | Status |
| :--- | :--- | :--- |
| Scaffold completo e código inicial pronto para teste real | `osha-safety-compliance-mcp` | ✅ |
| Teste real com `DOL_API_KEY` + ajustes de schema/campos da API DOL | `osha-safety-compliance-mcp` | ✅ |
| Publicação na Apify Store com precificação PPE ($5.00/1k) | `osha-safety-compliance-mcp` | ✅ |
| Pesquisa de endpoints reais + scaffold completo | `epa-echo-environmental-mcp` | ✅ |
| Teste real e publicação na Apify Store | `epa-echo-environmental-mcp` | ✅ |
| Pesquisa de endpoints reais + scaffold completo | `fmcsa-carrier-safety-mcp` | ✅ |
| Teste real e publicação na Apify Store com PPE ($5.00/1k) | `fmcsa-carrier-safety-mcp` | ✅ |
| Pesquisa de endpoints USITC HTS + scaffold + testes unitários e smoke test | `usitc-hts-tariff-mcp` | ✅ |
| Publicação do Actor #4 / Projeto #3 na Apify Store com PPE ($5.00/1k) | `usitc-hts-tariff-mcp` | ✅ |
| Motor 51 estados 2026 + testes unitários do Actor #5 | `us-1099-nec-state-compliance-mcp` | ✅ |
| Publicação do Actor #5 na Apify Store com PPE ($5.00/1k) | `us-1099-nec-state-compliance-mcp` | ✅ |

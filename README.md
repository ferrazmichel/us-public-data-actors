# US Public Data Actors & MCP Tools (Apify Store Portfolio)

> Portfólio de Apify Actors e ferramentas compatíveis com **MCP (Model Context Protocol)** que transformam bases públicas oficiais dos Estados Unidos em dados limpos, paginados e prontos para agentes de IA e equipes B2B de compliance, logística e vendas.

---

## Arquitetura do Portfólio

```text
us-public-data-actors/
├── AGENTS.md
├── docs/
│   ├── PLANO_DE_NEGOCIOS.md       # Estudo de mercado, concorrência e precificação PPE
│   ├── ROADMAP_ACTORS.md          # Especificação dos 3 primeiros Actors + backlog
│   └── GUIA_INICIO_FERIADO.md     # Checklist passo a passo para testar e publicar em casa
└── actors/
    ├── osha-safety-compliance-mcp/ # Actor #1 (Publicado)
    ├── epa-echo-environmental-mcp/ # Actor #2 (Publicado)
    ├── fmcsa-carrier-safety-mcp/          # Actor #3 (Publicado)
    ├── usitc-hts-tariff-mcp/              # Actor #4 / Projeto #3 (Publicado)
    ├── us-1099-nec-state-compliance-mcp/  # Actor #5 (Publicado)
    ├── openfda-recall-device-radar/       # Actor #6 (Publicado)
    └── sec-edgar-filings-mcp/             # Actor #7 (Build Apify pronto para publicação)
```

---

## Actors Planejados

| Ordem | Slug do Actor | Fonte Oficial EUA | Público / Caso de Uso | Status |
| :--- | :--- | :--- | :--- | :--- |
| **#1** | [`osha-safety-compliance-mcp`](actors/osha-safety-compliance-mcp) | DOL / OSHA Enforcement API (`apiprod.dol.gov/v4`) | Due diligence de fornecedores, seguradoras, escritórios jurídicos e agentes B2B | Publicado na Apify Store (PPE $5/1k) ✅ |
| **#2** | [`epa-echo-environmental-mcp`](actors/epa-echo-environmental-mcp) | EPA ECHO REST API (`echodata.epa.gov`) | Consultorias ESG/ambientais, due diligence imobiliária e industrial | Publicado na Apify Store (PPE $5/1k) ✅ |
| **#3** | [`fmcsa-carrier-safety-mcp`](actors/fmcsa-carrier-safety-mcp) | USDOT / FMCSA (`data.transportation.gov`) | Seguradoras de carga, corretoras de frete, factoring e recrutamento | Publicado na Apify Store (PPE $5/1k) ✅ |
| **#4 (Proj. #3)** | [`usitc-hts-tariff-mcp`](actors/usitc-hts-tariff-mcp) | USITC HTS REST API (`hts.usitc.gov`) | Importadores EUA, lojistas Shopify/Amazon FBA, despachantes e agentes de sourcing | Publicado na Apify Store (PPE $5/1k) ✅ |
| **#5** | [`us-1099-nec-state-compliance-mcp`](actors/us-1099-nec-state-compliance-mcp) | IRS IRC § 6041A / Regras Estaduais 2026 (50 Estados + DC) | Contadores (CPAs), ERPs, PMEs e agentes financeiros (trava \$2.000 vs. \$600 + 24% backup withholding) | Publicado na Apify Store (PPE $5/1k) ✅ |
| **#6** | [`openfda-recall-device-radar`](actors/openfda-recall-device-radar) | openFDA Enforcement APIs (`api.fda.gov`) | Hospitais, farmácias, escritórios jurídicos e supply chain (recalls Class I/II/III) | Publicado na Apify Store (PPE $5/1k) ✅ |
| **#7** | [`sec-edgar-filings-mcp`](actors/sec-edgar-filings-mcp) | SEC EDGAR Submissions & XBRL Facts (`data.sec.gov`) | Equity research, analistas financeiros, fintechs e agentes de IA (10-K/10-Q/8-K) | Build & deploy na Apify pronto para publicação 🚧 |

---

## Pré-requisitos para Executar Localmente (em Casa)

- Python **3.12+**
- Conta gratuita na [Apify](https://apify.com) e `apify-cli` (ou `docker`)
- Chave gratuita da API do Departamento do Trabalho dos EUA (DOL) para o Actor #1 (instruções detalhadas em [`docs/GUIA_INICIO_FERIADO.md`](docs/GUIA_INICIO_FERIADO.md))

---

## Documentação

- [`docs/PLANO_DE_NEGOCIOS.md`](docs/PLANO_DE_NEGOCIOS.md)
- [`docs/ROADMAP_ACTORS.md`](docs/ROADMAP_ACTORS.md)
- [`docs/GUIA_INICIO_FERIADO.md`](docs/GUIA_INICIO_FERIADO.md)

---

## Tabela de Atividades

| Atividade | Responsável | Status |
| :--- | :--- | :--- |
| Definir plano de negócios, precificação PPE e análise de concorrência | IA | ✅ |
| Estruturar scaffold completo do Actor #1 (`osha-safety-compliance-mcp`) | IA | ✅ |
| Subir repositório para o GitHub pessoal (`ferrazmichel/us-public-data-actors`) | Usuário | ✅ |
| Solicitar `DOL_API_KEY` gratuita e executar teste real ponta a ponta no feriado | Usuário | ✅ |
| Ajustar eventual detalhe de endpoint/campos após retorno real da API DOL | IA + Usuário | ✅ |
| Publicar Actor #1 na Apify Store com cobrança PPE e suporte MCP | Usuário + IA | ✅ |
| Construir e publicar Actor #2 (`epa-echo-environmental-mcp`) na Apify Store | IA + Usuário | ✅ |
| Construir e publicar Actor #3 (`fmcsa-carrier-safety-mcp`) na Apify Store | IA + Usuário | ✅ |
| Construir Projeto #3 / Actor #4 (`usitc-hts-tariff-mcp`) e subir build na Apify | IA | ✅ |
| Ajustar memória (512 MB), configurar PPE ($5/1k) e publicar Actor #4 na Apify Store | Usuário | ✅ |
| Construir Actor #5 (`us-1099-nec-state-compliance-mcp`) e subir build na Apify | IA | ✅ |
| Ajustar memória (512 MB), configurar PPE ($5/1k) e publicar Actor #5 na Apify Store | Usuário | ✅ |
| Construir Actor #6 (`openfda-recall-device-radar`) e subir build na Apify | IA | ✅ |
| Ajustar memória (512 MB), configurar PPE ($5/1k) e publicar Actor #6 na Apify Store | Usuário | ✅ |
| Construir Actor #7 (`sec-edgar-filings-mcp`) e subir build na Apify | IA | ✅ |
| Ajustar memória (512 MB), configurar PPE ($5/1k) e publicar Actor #7 na Apify Store | Usuário | ⬜ |

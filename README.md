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
    └── osha-safety-compliance-mcp/ # Actor #1 (MVP pronto para teste real com DOL_API_KEY)
```

---

## Actors Planejados

| Ordem | Slug do Actor | Fonte Oficial EUA | Público / Caso de Uso | Status |
| :--- | :--- | :--- | :--- | :--- |
| **#1** | [`osha-safety-compliance-mcp`](actors/osha-safety-compliance-mcp) | DOL / OSHA Enforcement API (`apiprod.dol.gov/v4`) | Due diligence de fornecedores, seguradoras, escritórios jurídicos e agentes B2B | Publicado na Apify Store (PPE $5/1k) ✅ |
| **#2** | [`epa-echo-environmental-mcp`](actors/epa-echo-environmental-mcp) | EPA ECHO REST API (`echodata.epa.gov`) | Consultorias ESG/ambientais, due diligence imobiliária e industrial | Publicado na Apify Store (PPE $5/1k) ✅ |
| **#3** | [`fmcsa-carrier-safety-mcp`](actors/fmcsa-carrier-safety-mcp) | USDOT / FMCSA (`data.transportation.gov`) | Seguradoras de carga, corretoras de frete, factoring e recrutamento | Construído, testado ao vivo e enviado para a Apify Platform ✅ |

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
| Construir, testar ao vivo e enviar Actor #3 (`fmcsa-carrier-safety-mcp`) para Apify Platform | IA + Usuário | ✅ |

# AGENTS.md — `us-public-data-actors`

> Diretrizes técnicas e comerciais para desenvolvimento e manutenção do portfólio de Apify Actors & ferramentas MCP baseadas em APIs públicas dos EUA.

---

## 1. Propósito do Repositório

- Construir um portfólio modular de **Apify Actors** e conectores **MCP (Model Context Protocol)** que entregam dados públicos oficiais dos EUA limpos, paginados e prontos para consumo por agentes de IA (Claude, Cursor, n8n, LangGraph, CrewAI) e pipelines B2B.
- Meta de contribuição no portfólio: **US\$ 150 a US\$ 350+ líquidos/mês** somando 3 a 5 Actors nichados e estáveis na Apify Store.

---

## 2. Regras Arquiteturais Obrigatórias

1. **API-First, Zero Scraping Frágil:**
   - Priorizar APIs oficiais e conjuntos de dados públicos do governo dos EUA (DOL/OSHA, EPA ECHO, USDOT/FMCSA, openFDA, SEC EDGAR, SAM.gov) antes de considerar HTML scraping.
   - Evitar depender de proxies residenciais caros sempre que houver endpoint REST/bulk público.
2. **Padrão MCP-Ready (Economia de Tokens e Baixa Latência):**
   - Toda saída deve ser JSON estruturado, limpo e normalizado (nunca despejar HTML bruto ou campos irrelevantes).
   - Todo Actor deve suportar um modo compacto (`mcp_summary`) além do detalhado (`detailed`), resumindo totais, riscos e métricas em poucos KB para agentes de IA.
   - Consultas pontuais devem responder em **< 30 segundos** para não dar timeout em sessões de chat de agentes MCP; habilitar **Standby Mode** quando aplicável na Apify.
3. **Estrutura Modular por Actor:**
   - Cada Actor fica isolado em `actors/<actor-slug>/` com seu próprio `.actor/`, `Dockerfile`, `requirements.txt`, `src/` e `README.md` (em **inglês nativo** otimizado para a Apify Store).
4. **Monetização via Pay-Per-Event (PPE):**
   - Projetar eventos claros de cobrança via `Actor.charge()` alinhados ao valor entregue (ex.: registro retornado, relatório detalhado de estabelecimento/empresa).
   - Nunca cobrar se uma chamada falhar antes de entregar dados válidos; tratar graciosamente o modo local sem cobrança ativa durante testes.
5. **Segurança e Credenciais:**
   - **Nunca** commitar `DOL_API_KEY`, `APIFY_TOKEN`, `EIA_API_KEY` ou quaisquer chaves/tokens em código ou `.actor/*.json`.
   - Receber segredos via variável de ambiente do Actor ou campo `isSecret: true` no `input_schema.json`.
6. **Validação Ponta a Ponta Obrigatória:**
   - Nunca considerar um Actor pronto apenas por sintaxe estática (`py_compile`). Sempre executar teste real contra a API governamental usando uma chave válida e validar o schema real do JSON retornado antes de publicar na Apify Store.

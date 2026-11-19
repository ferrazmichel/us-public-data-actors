# Plano de Negócios — Portfólio de Actors & Ferramentas MCP (Apify Store)

> **Data de referência:** 19/11/2026  
> **Estratégia:** Construir um portfólio de 3 a 5 Apify Actors nichados em dados regulatórios/públicos dos EUA (API-first + prontos para MCP) com renda recorrente por uso em dólar.

---

## 1. Por Que a Apify Store + MCP em 2026?

1. **Distribuição e cobrança terceirizadas:** A Apify distribui entre **US\$ 1,6 milhão e US\$ 2,0 milhões por mês** entre criadores da loja e cuida de hospedagem, autenticação OAuth, faturamento com cartão global e repasse mensal via **Wise** (mínimo US\$ 20).
2. **Nova onda de compradores (Agentes de IA via MCP):** Com o servidor MCP oficial da Apify (`mcp.apify.com`), agentes autônomos (Claude, Cursor, LangGraph, CrewAI, n8n) buscam e chamam Actors programaticamente. Quem entrega **JSON limpo, rápido (<30s) e compacto em tokens** passa a ser consumido diretamente por fluxos automatizados.
3. **Economia unitária favorável para APIs governamentais:**
   $$\text{Repasse} = (0{,}80 \times \text{Receita Bruta}) - \text{Custos de Plataforma}$$
   Como nossos Actors consultam APIs JSON oficiais com `httpx` (sem rodar Chromium pesado nem pagar proxies residenciais caros), o custo de plataforma por execução é minúsculo, mantendo margem líquida muito próxima dos **80% da Apify**.

---

## 2. Análise Competitiva Real (Pesquisa de 19/11/2026)

| Vertical Pública EUA | Oferta Atual na Apify Store | Demanda B2B | Decisão Estratégica |
| :--- | :--- | :--- | :--- |
| **OSHA (Segurança do Trabalho / Multas)** | **Muito baixa:** apenas ~2 Actors visíveis (`ryanclinton/osha-inspection-search` e um concorrente marcado como depreciado/em manutenção) | Alta: seguradoras, due diligence M&A, escritórios trabalhistas, SDRs vendendo software/EPI | **Prioridade #1 (MVP):** menos concorrência e necessidade clara de saída compacta MCP + join automático de violações |
| **EPA ECHO (Conformidade Ambiental)** | Baixa: exige fluxo em 2 etapas (query ID + paginação + DFR) que poucos automatizam bem | Alta: consultorias ESG/ambientais, due diligence imobiliária, investidores | **Prioridade #2:** ótimo diferencial técnico empacotar as 2 etapas + relatório estruturado |
| **FMCSA / USDOT (Transportadoras)** | Média: há players focados em novos cadastros/leads | Muito alta: seguradoras de frete, factoring, corretoras, compliance logístico | **Prioridade #3:** combinar consulta pontual MCP (vetting de risco) + extração em lote |
| **SAM.gov / NPPES NPI** | Média-Alta (4–5+ competidores ativos) | Muito alta | Ficar no backlog apenas para ângulo muito específico no futuro |

---

## 3. Modelo de Precificação (Pay-Per-Event — PPE)

A Apify substituiu modelos antigos de aluguel fixo pelo **Pay-Per-Event (`Actor.charge()`)**, que escala melhor com uso por agentes MCP.

### Estrutura sugerida para o Actor #1 (`osha-safety-compliance-mcp`)
- **`actor-start` (ou taxa base leve por execução):** ~US\$ 0,005 a US\$ 0,01 por chamada (cobre inicialização e evita abuso de chamadas vazias).
- **`inspection-record`:** **US\$ 0,004 a US\$ 0,008 por inspeção retornada** (ex.: 100 inspeções = US\$ 0,40–0,80; 1.000 inspeções = US\$ 4–8).
- **`mcp-summary` (opcional se quiser simplificar para agentes):** US\$ 0,02 por resumo executivo consolidado de uma empresa.

> **Regra de lançamento:** começar ligeiramente mais barato ou com margem generosa nas primeiras 4 semanas para conquistar os primeiros usuários recorrentes, taxa de sucesso > 98% e avaliações positivas no ranking da loja, ajustando preço depois conforme custo real observado.

---

## 4. Projeção Progressiva para Contribuir à Meta do Portfólio

| Estágio | Escopo | Uso Médio Estimado | Receita Bruta Estimada | Repasse Estimado (~75–78% líq. Apify) |
| :--- | :--- | :--- | :--- | :--- |
| **Estágio 1 (Mês 1–2)** | 1 Actor publicado (OSHA) | 5–10 usuários B2B/agentes | US\$ 30 – US\$ 80/mês | US\$ 23 – US\$ 62/mês |
| **Estágio 2 (Mês 3–4)** | 3 Actors (OSHA + EPA + FMCSA) | 20–40 usuários recorrentes | US\$ 150 – US\$ 280/mês | US\$ 115 – US\$ 215/mês |
| **Estágio 3 (Mês 5–8)** | 4–5 Actors otimizados para MCP + SEO no README | 40–80 usuários / pipelines | US\$ 300 – US\$ 500+/mês | **US\$ 230 – US\$ 390+/mês** |

Combinado com o Projeto #2 (`us-home-energy-calcs`), esse portfólio cobre a meta total com folga e sem depender de um único produto.

---

## 5. Estratégia de Aquisição Sem Marketing Pago

1. **README de alta conversão (em inglês):** mostrar caso de uso B2B em 10 segundos, exemplo real de JSON retornado e bloco pronto para copiar no `.mcp.json` de Claude/Cursor.
2. **Standby Mode + Schemas completos:** preencher `input_schema.json`, `output_schema.json` e `dataset_schema.json` aumenta a nota de qualidade no ranking interno da Apify Store.
3. **Semente inicial gratuita (1–2 posts orgânicos):** após validado em produção, publicar um guia prático curto no Dev.to / GitHub / comunidades MCP mostrando como usar agentes de IA para checar risco trabalhista (OSHA) ou ambiental (EPA) de fornecedores — atraindo os primeiros usuários sem custo de anúncio.

---

## Tabela de Atividades

| Atividade | Responsável | Status |
| :--- | :--- | :--- |
| Levantar concorrentes reais na Apify Store (OSHA, EPA, FMCSA, SAM, NPPES, FDA) | IA | ✅ |
| Definir estratégia de precificação Pay-Per-Event e posicionamento MCP | IA | ✅ |
| Validar custos reais de plataforma na primeira execução em produção na Apify | Usuário + IA | ⬜ |
| Ajustar preços PPE após as primeiras 20 execuções pagas | Usuário + IA | ⬜ |

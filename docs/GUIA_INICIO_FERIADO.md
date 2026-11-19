# Guia Prático de Início em Casa (Feriado / Fim de Semana)

> Siga este passo a passo no seu computador pessoal para validar o **Actor #1 (`osha-safety-compliance-mcp`)** com dados reais e publicá-lo na Apify Store.

---

## Passo 1 — Pré-requisitos na Máquina Pessoal

1. Certifique-se de ter **Python 3.12+** instalado (`python --version`).
2. Instale o **Node.js 20 LTS** (necessário para o `apify-cli` e também para o Projeto #2) e depois instale a CLI da Apify:
   ```bash
   npm install -g apify-cli
   ```
3. Verifique se tem **Docker Desktop** (opcional para build local; o `apify push` constrói na nuvem da Apify automaticamente mesmo sem Docker local).

---

## Passo 2 — Criar Contas Gratuitas (Apify + DOL API Key)

1. **Conta Apify:**
   - Crie uma conta pessoal em [https://apify.com](https://apify.com).
   - No console da Apify, confira **Settings → Billing / Payouts** quando for habilitar monetização (suporta **Wise** para receber no Brasil a partir de US\$ 20).
2. **Chave Gratuita da API do Departamento do Trabalho dos EUA (DOL):**
   - Acesse o portal oficial do DOL Open Data:
     - Documentação: `https://usdepartmentoflabor.github.io/Developer/health-and-safety/dol-osha-enforcement/`
     - Portal / Registro de chave: `https://dataportal.dol.gov/` (ou link indicado no Beginner's Guide da DOL).
   - Crie sua conta gratuita e gere uma **API Key**. Guarde em lugar seguro (nunca commitar no Git).

---

## Passo 3 — Configurar Ambiente Local e Testar Chamada Real

Entre na pasta do Actor #1:

```bash
cd us-public-data-actors/actors/osha-safety-compliance-mcp
python -m venv .venv
```

Ative o ambiente virtual (Windows PowerShell):

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Crie o arquivo `.env` a partir do `.env.example` (o `.env` está no `.gitignore`) e preencha sua chave real:

```powershell
Copy-Item .env.example .env
# Edite .env e preencha DOL_API_KEY=sua_chave_aqui
```

### ⚠️ Teste obrigatório de contrato da API DOL (Regra de validação ponta a ponta)
Antes de publicar na loja, valide se os endpoints e parâmetros da versão ativa da API DOL (`https://data.dol.gov/get/` ou v4 `apiv4.dol.gov`) respondem exatamente com os nomes de tabela/colunas usados em `src/dol_client.py` (`osha/inspection` e `osha/violation`).

Rode primeiro um teste rápido via Python/curl ou execute o Actor localmente com `apify run`:

```powershell
$env:DOL_API_KEY="SUA_CHAVE_AQUI"
apify run -i '{"establishmentName": "Amazon", "state": "TX", "maxRecords": 5, "includeViolations": true, "outputMode": "mcp_summary"}'
```

**O que observar no resultado:**
- Se retornar código `200` e os registros aparecerem em `storage/datasets/default/` e `storage/key_value_stores/default/OUTPUT.json`, confira os campos reais devolvidos pela API.
- Se a API retornar `404` ou formato de filtro diferente (a DOL mantém transição de rotas `get/` vs `v4`), **copie exatamente a URL e o JSON de erro/documentação exibidos no terminal** e cole na nossa próxima conversa no trabalho/casa que eu ajusto o `dol_client.py` na hora!

---

## Passo 4 — Publicar na Apify Store e Ativar MCP

1. Faça login na CLI:
   ```bash
   apify login
   ```
2. Dentro de `actors/osha-safety-compliance-mcp`, suba o Actor para sua conta Apify:
   ```bash
   apify push
   ```
3. No **Apify Console** (interface web):
   - Abra o Actor enviado → execute 2 ou 3 testes diretamente pela aba **Try me / Input** (configure `DOL_API_KEY` como variável de ambiente secreta padrão do Actor caso queira cobrir chamadas de clientes sem que o cliente precise ter chave própria — ou documente ambos os modos).
   - Em **Publication → Monetization**, configure o modelo **Pay-Per-Event (PPE)** definindo o evento `inspection-record` (ex.: US\$ 0,005/registro) e opcionalmente `actor-start` (ex.: US\$ 0,005).
   - Habilite **Standby Mode** se desejar resposta imediata para agentes via `mcp.apify.com`.
   - Publique na **Apify Store**!

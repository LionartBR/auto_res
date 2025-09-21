# Guia do Projeto SIREP 2.0

## Índice
- [Visão geral do repositório](#visão-geral-do-repositório)
- [Estrutura de diretórios](#estrutura-de-diretórios)
- [Configuração do ambiente](#configuração-do-ambiente)
- [Execução da aplicação](#execução-da-aplicação)
- [Padrões de código](#padrões-de-código)
  - [Python](#python)
  - [SQL](#sql)
  - [Frontend (HTML/CSS/JS)](#frontend-htmlcssjs)
- [Banco de dados e configuração](#banco-de-dados-e-configuração)
- [Testes automatizados e qualidade](#testes-automatizados-e-qualidade)
- [Registros e observabilidade](#registros-e-observabilidade)
- [Checklist antes do commit](#checklist-antes-do-commit)
- [Boas práticas para PRs](#boas-práticas-para-prs)

## Visão geral do repositório
Este repositório contém o código do **SIREP 2.0**, uma aplicação FastAPI focada na coleta, orquestração e exposição de planos e ocorrências.
A stack principal inclui Python 3.13+, FastAPI, SQLAlchemy, Pydantic e SQLite.

## Estrutura de diretórios
| Caminho | Descrição |
| --- | --- |
| `sirep/app/` | Camada de entrada (API FastAPI, CLI e fluxos de captura). |
| `sirep/adapters/` | Adaptadores para serviços externos ou integrações específicas. |
| `sirep/domain/` | Modelos ORM, esquemas Pydantic, enums e regras de domínio. |
| `sirep/infra/` | Configurações, logging e acesso a banco de dados. |
| `sirep/services/` | Casos de uso e orquestrações de etapas de captura. |
| `sirep/shared/` | Utilitários compartilhados (idempotência, retries etc.). |
| `sirep/sql/` | Scripts SQL auxiliares (ex.: criação inicial do schema). |
| `sirep/ui/` | Interface web estática servida pela API. |
| `tests/` | Testes automatizados (pytest). |

## Configuração do ambiente
1. Garanta Python 3.13+ instalado.
2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   ```
3. Instale as dependências principais listadas em `sirep/pyproject.toml` (ainda não há configuração para `pip install -e`):
   ```bash
   pip install fastapi uvicorn pydantic SQLAlchemy pydantic-settings tenacity python-dotenv
   ```
4. Instale as ferramentas de teste e suporte:
   ```bash
   pip install pytest pytest-asyncio httpx anyio
   ```
5. Garanta que o diretório do repositório esteja no `PYTHONPATH` antes de rodar scripts/testes:
   ```bash
   export PYTHONPATH="$PWD:$PYTHONPATH"
   ```
6. Opcional: instale ferramentas de qualidade sugeridas (`ruff`, `black`, `mypy`).

## Execução da aplicação
- API: `python -m sirep.app.cli serve --host 0.0.0.0 --port 8000`
- CLI para execução das etapas de captura: `python -m sirep.app.cli run --steps ETAPA_1,...`
- O frontend estático pode ser acessado em `/app/` após iniciar o servidor.

## Padrões de código
### Python
- Utilize **type hints** em funções públicas e classe.
- Prefira docstrings concisas (formato Google ou reST) em serviços, adapters e endpoints.
- Mantenha o estilo PEP 8 (linhas ≤ 100 colunas, imports agrupados por padrão).
- Quando lidar com contexto de banco, use `SessionLocal()` com `try/finally` ou context manager.
- Centralize regras de domínio em `sirep/domain/` e evite repetir lógica nas camadas superiores.
- Não capture exceções genéricas sem registrar (`logger.exception`) e relembrar contexto.

### SQL
- Scripts `sirep/sql/` devem ser idempotentes e documentados com comentários em português.
- Sempre valide manualmente queries no SQLite local antes de automatizar na aplicação.
- Priorize o uso de SQLAlchemy ORM; use SQL bruto somente quando indispensável (documente o motivo).

### Frontend (HTML/CSS/JS)
- Mantenha o HTML semântico e acessível (`aria-*`, roles, labels).
- Centralize estilos em classes; evite estilos inline permanentes.
- Se adicionar JS, prefira módulos e funções puras; isole chamadas à API em utilitários.
- Atualize documentação de endpoints quando o frontend passar a consumi-los.

## Banco de dados e configuração
- As configurações ficam em `sirep/infra/config.py` via `pydantic-settings`.
- Variáveis de ambiente usam prefixo `SIREP_` (ex.: `SIREP_DB_URL`, `SIREP_RUNTIME_ENV`).
- O banco padrão é SQLite (`sqlite:///./sirep.db`). Para testes, use `SIREP_RUNTIME_ENV=test` e bancos temporários.
- Ao introduzir novas tabelas/colunas, atualize:
  1. Modelos em `sirep/domain/models.py`.
  2. Schemas Pydantic correspondentes.
  3. Scripts em `sirep/sql/` (quando necessário).
  4. Dados seeds/migrações.

## Testes automatizados e qualidade
- Rodar toda a suíte: `pytest` (executa em `tests/`).
- Testes que interagem com banco devem usar fixtures para isolar o ambiente.
- Ao adicionar endpoint, inclua teste de rota equivalente.
- Para serviços assíncronos, considere `pytest-asyncio` e `anyio`.
- Antes de subir, rode ferramentas de lint/format que estiver usando.

## Registros e observabilidade
- O logging padrão é configurado por `sirep.infra.logging.setup_logging` e grava em `sirep/logs/sirep.log` + console.
- Não comite arquivos de log grandes; se precisar de novos handlers, configure-os centralmente.
- Ao capturar erros, inclua contexto relevante no log (numero_plano, etapa etc.).

## Checklist antes do commit
- [ ] Código formatado e com type hints atualizados.
- [ ] Novas dependências documentadas neste arquivo (se aplicável).
- [ ] Testes relevantes atualizados/criados.
- [ ] `pytest` executado e passando localmente.
- [ ] Logs/artefatos temporários removidos.
- [ ] Arquivos terminam com newline.

## Boas práticas para PRs
- Descreva claramente o problema e a solução.
- Inclua resumo das mudanças, impacto em banco/API e passos de teste.
- Adicione capturas de tela quando alterar `sirep/ui/`.
- Mantenha commits pequenos e com mensagens descritivas (pt-BR ou en-US consistentes).
- Solicite revisão de alguém familiar com a área impactada (app, services, infra, frontend etc.).


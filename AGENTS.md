# Guia do Projeto SIREP 2.0 (atualizado em outubro/2024)

## Índice
- [Visão geral do repositório](#visão-geral-do-repositório)
- [Stack e dependências](#stack-e-dependências)
- [Estrutura de diretórios](#estrutura-de-diretórios)
- [Configuração do ambiente](#configuração-do-ambiente)
- [Execução e scripts úteis](#execução-e-scripts-úteis)
- [Banco de dados](#banco-de-dados)
- [Padrões de código](#padrões-de-código)
  - [Python](#python)
  - [SQL](#sql)
  - [Frontend (HTML/CSS/JS)](#frontend-htmlcssjs)
- [Testes e qualidade](#testes-e-qualidade)
- [Observabilidade e registros](#observabilidade-e-registros)
- [Checklist antes do commit](#checklist-antes-do-commit)
- [Boas práticas para PRs](#boas-práticas-para-prs)

## Visão geral do repositório
Este repositório contém o código do **SIREP 2.0**, uma aplicação FastAPI focada na coleta, orquestração e exposição de
planos e ocorrências. A aplicação expõe uma API, uma camada de orquestração de etapas (pipeline de captura/tratamento)
e uma interface web estática.

## Stack e dependências
- **Python**: 3.13 ou superior.
- **Principais bibliotecas** (vide `sirep/pyproject.toml`): `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`,
  `SQLAlchemy`, `python-dotenv`, `tzdata`.
- **Ferramentas de apoio para desenvolvimento/testes**: `pytest`, `pytest-asyncio`, `httpx`, `anyio`.
- Ferramentas opcionais recomendadas: `ruff`, `black`, `mypy`, `pre-commit`.

> Ainda não há `pyproject` no nível da raiz ou `setup.cfg`. Instale as dependências manualmente (veja a próxima seção).

## Estrutura de diretórios
| Caminho | Descrição |
| --- | --- |
| `sirep/app/` | API FastAPI, CLI (`python -m sirep.app.cli`) e fluxos de captura/tratamento. |
| `sirep/adapters/` | Adaptadores/stubs para integrações externas. |
| `sirep/domain/` | Modelos ORM, esquemas Pydantic, enums, eventos e regras de domínio. |
| `sirep/infra/` | Configurações, logging, camada de acesso ao banco, repositórios. |
| `sirep/services/` | Casos de uso, helpers de orquestração e execução das etapas. |
| `sirep/sql/` | Scripts SQL auxiliares (ex.: bootstrap inicial `001_init.sql`). |
| `sirep/scripts/` | Scripts utilitários (reset do banco, execução do pipeline de demonstração). |
| `sirep/tools/` | Ferramentas auxiliares (ex.: exportação de artefatos). |
| `sirep/ui/` | Interface estática servida pela API (`/app`). |
| `sirep/logs/` | Saída padrão de logs (`logs/sirep.log`). Não comite arquivos grandes. |
| `sirep/sirep.db` | Banco SQLite padrão de desenvolvimento/demo. |
| `tests/` | Testes automatizados com pytest. |

## Configuração do ambiente
1. Garanta Python 3.13+ instalado e atualizado (`python --version`).
2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   python -m pip install --upgrade pip
   ```
3. Instale as dependências de runtime manualmente (enquanto não temos pacote publicável):
   ```bash
   pip install fastapi uvicorn pydantic "pydantic-settings" SQLAlchemy python-dotenv tzdata
   ```
4. Instale ferramentas de teste/desenvolvimento:
   ```bash
   pip install pytest pytest-asyncio httpx anyio
   ```
5. (Opcional) Ferramentas de qualidade sugeridas:
   ```bash
   pip install ruff black mypy pre-commit
   ```
6. Certifique-se de que o diretório do repositório esteja no `PYTHONPATH` ao rodar scripts fora dos testes:
   ```bash
   export PYTHONPATH="$PWD:$PYTHONPATH"
   ```

## Execução e scripts úteis
- **API**: `python -m sirep.app.cli serve --host 0.0.0.0 --port 8000`
- **Pipeline via CLI**: `python -m sirep.app.cli run --steps ETAPA_1,ETAPA_2,...`
- **Uvicorn direto** (quando o pacote estiver instalado no ambiente): `uvicorn sirep.app.api:app --reload`
- **Reset do banco**: `python -m sirep.scripts.reset_db`
- **Execução de pipeline demonstrativo**: `python -m sirep.scripts.run_pipeline`
- **Ferramenta auxiliar**: `python -m sirep.tools.export_repo_txt`

A interface estática fica acessível em `/app/` após iniciar o servidor FastAPI.

## Banco de dados
- Configurações carregadas via `sirep.infra.config.Settings` (prefixo `SIREP_`). Variáveis relevantes: `SIREP_DB_URL`,
  `SIREP_RUNTIME_ENV`, `SIREP_DRY_RUN`, `SIREP_LOG_LEVEL`.
- Banco padrão: `sqlite:///./sirep.db`. O arquivo `sirep/sirep.db` serve como base de desenvolvimento e pode ser
  regenerado com `reset_db.py`.
- `init_db()` (chamado ao subir a API/testes) garante criação do schema e adiciona colunas legadas automaticamente.
- Para testes que interagem com o banco, utilize as fixtures do pytest (`SessionLocal`) para isolar o estado.

## Padrões de código
### Python
- Utilize **type hints** e mantenha docstrings curtas (formato Google ou reST) para serviços, adapters e endpoints.
- Estilo geral: PEP 8, limite de 100 colunas, imports agrupados por tipo.
- Utilize `SessionLocal()` via context manager (`with`/`try-finally`) e os repositórios definidos em `sirep.infra.repositories`.
- Centralize regras de domínio em `sirep/domain` para evitar duplicidade nas camadas superiores.
- Ao tratar exceções, registre o contexto com `logger.exception` ou `logger.error` (veja `sirep.infra.logging`).

### SQL
- Scripts em `sirep/sql/` devem ser idempotentes, versionados e documentados em português.
- Prefira o ORM do SQLAlchemy; use SQL bruto apenas quando necessário e documente o motivo no código.
- Valide manualmente queries críticas no SQLite local antes de automatizá-las.

### Frontend (HTML/CSS/JS)
- Mantenha HTML semântico, com atributos de acessibilidade (`aria-*`, roles, labels).
- Centralize estilos em classes e evite estilos inline permanentes.
- Se adicionar JS, utilize módulos/funções puras e isole chamadas HTTP em utilitários.
- Atualize documentação de endpoints quando o frontend passar a consumi-los.

## Testes e qualidade
- Rode a suíte completa com `pytest`. Utilize `pytest -k <pattern>` para executar subconjuntos quando necessário.
- Testes que manipulam banco devem limpar/seedar dados via fixtures (`SessionLocal`, `init_db`).
- Antes de abrir PR, execute as ferramentas de lint/format que estiver usando (ex.: `ruff check`, `black`, `mypy`).
- Considere adicionar testes para novos endpoints/casos de uso criados.

## Observabilidade e registros
- Logging configurado por `sirep.infra.logging.setup_logging` (chamado pela API). Por padrão escreve em console e em
  `logs/sirep.log` com rotação. Ajuste via `LOG_DIR`/`LOG_LEVEL`.
- Não comite arquivos de log gerados durante desenvolvimento; mantenha apenas exemplos pequenos se necessários.
- Inclua contexto relevante nos logs (número do plano, etapa, identificadores externos) ao capturar erros.

## Checklist antes do commit
- [ ] Código formatado, lintado e com type hints atualizados.
- [ ] Novas dependências documentadas neste arquivo (quando aplicável).
- [ ] Testes relevantes atualizados/criados.
- [ ] `pytest` executado e passando localmente.
- [ ] Logs/artefatos temporários removidos.
- [ ] Arquivos finalizados com newline.

## Boas práticas para PRs
- Descreva claramente problema, solução e impacto em banco/API.
- Inclua resumo das mudanças, passos de teste e impactos em integrações externas.
- Adicione capturas de tela quando alterar algo em `sirep/ui/`.
- Mantenha commits pequenos, mensagens descritivas (pt-BR ou en-US consistentes) e siga convenções de branches padrão.
- Solicite revisão de alguém familiar com a área impactada (app, services, infra, frontend etc.).

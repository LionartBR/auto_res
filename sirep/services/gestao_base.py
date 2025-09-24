from __future__ import annotations

import html
import json
import logging
import math
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import md5
from time import sleep
from typing import Callable, Iterable, Iterator, List, Optional, Protocol, Tuple

from sirep.domain.enums import PlanStatus, Step
from sirep.infra.config import settings
from sirep.services.base import ServiceResult, StepJobContext, StepJobOutcome, run_step_job

logger = logging.getLogger(__name__)

try:  # pragma: no cover - depende de ambiente externo
    from pw3270 import PW3270
except Exception:  # pragma: no cover - biblioteca opcional
    PW3270 = None  # type: ignore[assignment]


# ---------------------------- Config / Constantes ----------------------------

DATA_LINES = range(10, 20)  # linhas onde estão os dados na E555
COL_START = 1
COL_WIDTH = 80

STATUS_HINT_POS = (21, 45, 21)  # "Linhas x a y de z"
FOOTER_MSG_POS = (22, 1, 80)  # Mensagens "FGEN2213"/"FGEN1389"

POS_E570_NUMERO = (6, 71)
POS_E570_RAZAO = (5, 18, 62)
POS_E570_SALDO = (20, 33, 47)
POS_E570_CNPJ = (4, 36, 16)

MAX_ATTEMPTS = 3
REQUEST_DELAY = 0.2

RESOLUCAO_DESCARTAR = "974/20"

MSG_FIM_BLOCO = "FGEN2213"
MSG_ULTIMA_PAGINA = "FGEN1389"


# ------------------------------ Utilitários ---------------------------------

def only_digits(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def parse_date_any(raw: str | None) -> Optional[date]:
    texto = (raw or "").strip()
    if not texto:
        return None
    formatos = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def parse_money_brl(raw: str | None) -> float:
    if raw is None:
        return math.nan
    texto = str(raw)
    negativo = "(" in texto and ")" in texto
    limpo = re.sub(r"[^\d.,-]", "", texto)
    limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = float(limpo)
    except ValueError:
        return math.nan
    return -valor if negativo else valor


# ---------------------------- Modelos de Dados ------------------------------

@dataclass(frozen=True)
class PlanRow:
    numero: str
    dt_propost: str
    tipo: str
    situac: str
    resoluc: str
    nome: str


@dataclass(frozen=True)
class PlanRowEnriched:
    numero: str
    dt_propost: str
    tipo: str
    situac: str
    resoluc: str
    razao_social: str
    saldo_total: str
    cnpj: str


@dataclass(frozen=True)
class GestaoBaseData:
    rows: List[PlanRowEnriched]
    raw_lines: List[str]
    portal_po: List[dict]
    descartados_974: int


class GestaoBaseCollector(Protocol):
    def collect(self) -> GestaoBaseData: ...


# ---------------------------- Helpers Terminais -----------------------------


def hash_lines(lines: Iterable[str]) -> str:
    return md5("\n".join(lines).encode()).hexdigest()


def parse_pagination(texto: str) -> Tuple[int, int, int]:
    match = re.search(r"Linhas\s+(\d+)\s+a\s+(\d+)\s+de\s+(\d+)", texto or "")
    if not match:
        raise ValueError(f"Formato inválido de paginação: '{texto}'")
    x, y, z = map(int, match.groups())
    return (x, z, z) if y == z else (x, y, z)


def parse_line(raw: str) -> Optional[PlanRow]:
    try:
        numero = raw[2:13].strip()
        dt_prop = raw[14:26].strip()
        tipo = raw[27:30].strip()
        situac = raw[31:41].strip()
        resoluc = raw[42:49].strip()
        nome = raw[54:].strip()
        if not numero:
            return None
        return PlanRow(numero, dt_prop, tipo, situac, resoluc, nome)
    except Exception as exc:  # pragma: no cover - proteção defensiva
        logger.warning("Erro ao parsear linha: %s - %s", raw[:60], exc)
        return None


def should_skip_line(raw: str) -> bool:
    texto = (raw or "").strip()
    return (not texto) or texto.startswith("Sel") or texto.startswith("Prox.Trans.")


@contextmanager
def session(pw: PW3270):  # pragma: no cover - integração externa
    pw.connect(delay=100)
    try:
        if not pw.is_connected():
            raise RuntimeError("Sem conexão ao Rede Caixa.")
        logger.info("Conectado ao Rede Caixa.")
        yield
    finally:
        pw.disconnect()
        if not pw.is_connected():
            logger.info("Sessão no Rede Caixa encerrada.")


def enter(pw: PW3270):  # pragma: no cover - integração externa
    pw.enter()
    pw.wait_status_ok()
    sleep(REQUEST_DELAY)


def pf(pw: PW3270, n: int):  # pragma: no cover - integração externa
    pw.send_pf_key(n)
    pw.wait_status_ok()
    sleep(REQUEST_DELAY)


def put(pw: PW3270, row: int, col: int, text: str):  # pragma: no cover
    pw.put_string(row, col, text)


def get_text(pw: PW3270, row: int, col: int, length: int) -> str:  # pragma: no cover
    return (pw.get_string(row, col, length) or "").strip()


def fill_and_enter(pw: PW3270, row: int, col: int, text: str):  # pragma: no cover
    put(pw, row, col, text)
    enter(pw)


def goto_tx(pw: PW3270, code: str):  # pragma: no cover
    fill_and_enter(pw, 21, 14, code)


def login_fge(pw: PW3270, senha: str):  # pragma: no cover
    fill_and_enter(pw, 17, 38, "611")
    fill_and_enter(pw, 9, 58, senha)
    fill_and_enter(pw, 4, 15, "FGE")


def open_e555(pw: PW3270):  # pragma: no cover
    goto_tx(pw, "E555")
    fill_and_enter(pw, 7, 18, "06")


def open_e570(pw: PW3270):  # pragma: no cover
    goto_tx(pw, "E570")


def read_page_lines(pw: PW3270) -> List[str]:  # pragma: no cover
    lines: List[str] = []
    for lin in DATA_LINES:
        raw = get_text(pw, lin, COL_START, COL_WIDTH)
        if not should_skip_line(raw):
            lines.append(raw)
    return lines


def read_pagination_hint(pw: PW3270) -> Tuple[int, int, int]:  # pragma: no cover
    hint = get_text(pw, *STATUS_HINT_POS)
    return parse_pagination(hint)


def read_footer_message(pw: PW3270) -> str:  # pragma: no cover
    return get_text(pw, *FOOTER_MSG_POS)


def iterate_e555_pages(
    pw: PW3270,
) -> Iterator[Tuple[List[str], Tuple[int, int, int], Optional[str]]]:  # pragma: no cover
    seen_hashes = set()
    attempts = 0

    while True:
        page_lines = read_page_lines(pw)
        page_hash = hash_lines(page_lines)

        if page_hash in seen_hashes:
            attempts += 1
            if attempts >= MAX_ATTEMPTS:
                raise RuntimeError("Loop detectado: página repetida")
        else:
            seen_hashes.add(page_hash)
            attempts = 0

        try:
            x, y, z = read_pagination_hint(pw)
            logger.info("Página: (%s, %s, %s) com %s entradas", x, y, z, len(page_lines))
        except ValueError as exc:
            attempts += 1
            logger.warning("%s", exc)
            if attempts >= MAX_ATTEMPTS:
                raise RuntimeError("Falha ao ler paginação")
            continue

        if y < z:
            yield (page_lines, (x, y, z), None)
            pf(pw, 8)
        else:
            yield (page_lines, (x, y, z), None)
            pf(pw, 8)
            footer = read_footer_message(pw)
            yield ([], (y, y, z), footer)
            break


def enrich_on_e570(pw: PW3270, rows: Iterable[PlanRow]) -> List[PlanRowEnriched]:  # pragma: no cover
    enriched: List[PlanRowEnriched] = []
    for row in rows:
        put(pw, *POS_E570_NUMERO, row.numero)
        enter(pw)
        razao = get_text(pw, *POS_E570_RAZAO)
        saldo = get_text(pw, *POS_E570_SALDO)
        cnpj = get_text(pw, *POS_E570_CNPJ)
        pf(pw, 9)
        enriched.append(
            PlanRowEnriched(
                row.numero,
                row.dt_propost,
                row.tipo,
                row.situac,
                row.resoluc,
                razao,
                saldo,
                cnpj,
            )
        )
    return enriched


# ---------------------------- Portal PO Helpers -----------------------------


def portal_po_provider() -> List[dict]:  # pragma: no cover - integração real
    import requests

    url = "https://seu-endpoint"
    payload = {"exemplo": 123}

    resp = requests.post(url, data=payload, timeout=60, verify=False)
    return parse_portal_po_json(resp.text)


def norm_plano(raw: str | None) -> str:
    return re.sub(r"\D", "", str(raw or "")).lstrip("0")


def parse_portal_po_json(json_text: str) -> List[dict]:
    try:
        data = json.loads(json_text)
        if not data or not data[0].get("result"):
            return []
        out: List[dict] = []
        for item in data[0].get("response", []):
            plano = norm_plano(item.get("cadastro_plano", ""))
            cnpj = str(item.get("cadastro_cnpj", item.get("cnpj", ""))).strip()
            tipo = str(html.unescape(item.get("tipo_descricao", item.get("tipo", "")))).strip()
            if plano:
                out.append({"Plano": plano, "CNPJ": cnpj, "Tipo": tipo})
        return out
    except Exception as exc:
        logger.warning("Falha ao parsear JSON do Portal PO: %s", exc)
        return []


def build_tipo_map(registros_po: List[dict]) -> dict[str, str]:
    tipos: dict[str, str] = {}
    for registro in registros_po:
        plano = norm_plano(registro.get("Plano"))
        tipo = str(registro.get("Tipo", "")).strip()
        if plano:
            tipos[plano] = tipo
    return tipos


def aplica_sit_especial_planrows(
    rows: List[PlanRow], tipos_por_plano: dict[str, str]
) -> List[PlanRow]:
    NOVA_SIT = "SIT. ESPECIAL (Portal PO)"
    ajustados: List[PlanRow] = []
    for row in rows:
        plano_norm = norm_plano(row.numero)
        if plano_norm in tipos_por_plano:
            ajustados.append(
                PlanRow(
                    row.numero,
                    row.dt_propost,
                    row.tipo,
                    NOVA_SIT,
                    row.resoluc,
                    row.nome,
                )
            )
        else:
            ajustados.append(row)
    return ajustados


# ------------------------------- Coleta ------------------------------------


def run_pipeline(
    pw: PW3270,
    senha: str,
    portal_provider: Optional[Callable[[], List[dict]]] = None,
) -> GestaoBaseData:  # pragma: no cover - integrações reais
    login_fge(pw, senha)
    open_e555(pw)

    blocos = 0
    raw_lines: List[str] = []
    all_rows: List[PlanRow] = []

    while True:
        blocos += 1
        logger.info("Iniciando bloco %s", blocos)
        footer_after_last: Optional[str] = None
        for page_lines, (_x, y, z), footer in iterate_e555_pages(pw):
            for line in page_lines:
                parsed = parse_line(line)
                if parsed:
                    all_rows.append(parsed)
                else:
                    raw_lines.append(line)
            if footer is not None:
                footer_after_last = footer

        footer_after_last = (footer_after_last or "").strip()
        if MSG_FIM_BLOCO in footer_after_last:
            logger.info("Fim do bloco, avançando para próximo bloco")
            pf(pw, 11)
            continue
        if MSG_ULTIMA_PAGINA in footer_after_last:
            logger.info("Última página, encerrando coleta da E555")
            break
        logger.warning("Mensagem inesperada no rodapé: %r", footer_after_last)
        break

    dados_filtrados = [row for row in all_rows if row.resoluc != RESOLUCAO_DESCARTAR]
    descartados_974 = len(all_rows) - len(dados_filtrados)

    portal_po: List[dict] = []
    if portal_provider:
        try:
            portal_po = portal_provider() or []
            logger.info("Portal PO: %s registros", len(portal_po))
        except Exception as exc:
            logger.warning("Falha ao obter Portal PO: %s", exc)
            portal_po = []

    tipos_map = build_tipo_map(portal_po) if portal_po else {}
    dados_ajustados = (
        aplica_sit_especial_planrows(dados_filtrados, tipos_map)
        if tipos_map
        else dados_filtrados
    )

    open_e570(pw)
    enriched = enrich_on_e570(pw, dados_ajustados)

    return GestaoBaseData(rows=enriched, raw_lines=raw_lines, portal_po=portal_po, descartados_974=descartados_974)


# ------------------------------- Serviço -----------------------------------


def _clean_inscricao(raw: str) -> str:
    texto = (raw or "").strip()
    return texto


def _persist_rows(context: StepJobContext, data: GestaoBaseData) -> dict[str, int]:
    inseridos = 0
    hoje = datetime.now(UTC).date()
    for row in data.rows:
        dt_proposta = parse_date_any(row.dt_propost)
        saldo_raw = parse_money_brl(row.saldo_total)
        saldo = None if math.isnan(saldo_raw) else saldo_raw
        inscricao = _clean_inscricao(row.cnpj)
        plan = context.plans.upsert(
            numero_plano=row.numero,
            gifug=None,
            situacao_atual=row.situac or None,
            situacao_anterior=row.situac or None,
            tipo=row.tipo or None,
            dt_situacao_atual=hoje,
            dt_proposta=dt_proposta,
            saldo=saldo,
            resolucao=row.resoluc or None,
            razao_social=row.razao_social or None,
            numero_inscricao=inscricao or None,
            representacao=inscricao or None,
            status=PlanStatus.PASSIVEL_RESC,
        )
        context.events.log(
            plan.id,
            Step.ETAPA_1,
            "Plano importado via Gestão da Base",
        )
        inseridos += 1
    return {
        "importados": inseridos,
        "descartados_974": data.descartados_974,
        "portal_po": len(data.portal_po),
    }


def _sample_data() -> GestaoBaseData:
    exemplos = [
        PlanRowEnriched(
            numero="1234567890",
            dt_propost="01/02/2024",
            tipo="PR1",
            situac="P.RESC.",
            resoluc="123/45",
            razao_social="Empresa Alfa Ltda",
            saldo_total="12.345,67",
            cnpj="12.345.678/0001-90",
        ),
        PlanRowEnriched(
            numero="2345678901",
            dt_propost="15/03/2024",
            tipo="PR2",
            situac="SIT. ESPECIAL (Portal PO)",
            resoluc="",  # mantém vazio
            razao_social="Empresa Beta S.A.",
            saldo_total="8.900,10",
            cnpj="98.765.432/0001-10",
        ),
    ]
    portal_po = [
        {"Plano": "2345678901", "CNPJ": "98.765.432/0001-10", "Tipo": "ESPECIAL"},
    ]
    return GestaoBaseData(rows=exemplos, raw_lines=[], portal_po=portal_po, descartados_974=0)


class DryRunCollector(GestaoBaseCollector):
    def collect(self) -> GestaoBaseData:
        logger.info("Executando coleta de Gestão da Base em modo dry-run")
        return _sample_data()


class TerminalCollector(GestaoBaseCollector):  # pragma: no cover - integrações reais
    def __init__(self, senha: str, portal_provider: Optional[Callable[[], List[dict]]] = None) -> None:
        if PW3270 is None:
            raise RuntimeError("Biblioteca pw3270 não disponível no ambiente")
        self.senha = senha
        self.portal_provider = portal_provider

    def collect(self) -> GestaoBaseData:
        assert PW3270 is not None
        pw = PW3270()
        with session(pw):
            return run_pipeline(pw, self.senha, portal_provider=self.portal_provider)


class GestaoBaseService:
    """Executa as etapas 1–4 da Gestão da Base utilizando a lógica da E555/E570."""

    def __init__(self, portal_provider: Optional[Callable[[], List[dict]]] = None) -> None:
        self.portal_provider = portal_provider or (portal_po_provider if not settings.DRY_RUN else None)

    def _collector(self, senha: Optional[str]) -> GestaoBaseCollector:
        if settings.DRY_RUN or senha is None:
            return DryRunCollector()
        return TerminalCollector(senha, self.portal_provider)

    def execute(self, senha: Optional[str] = None) -> ServiceResult:
        """Executa a captura de Gestão da Base e persiste os registros."""

        def _run(context: StepJobContext) -> StepJobOutcome:
            collector = self._collector(senha)
            data = collector.collect()
            resultado = _persist_rows(context, data)
            summary = f"{resultado['importados']} planos"
            return StepJobOutcome(data=resultado, info_update={"summary": summary})

        return run_step_job(step=Step.ETAPA_1, job_name=Step.ETAPA_1, callback=_run)


class GestaoBaseNoOpService:
    """Serviço auxiliar para etapas 2-4 que já são cobertas pela captura consolidada."""

    def __init__(self, step: Step) -> None:
        self.step = step

    def execute(self) -> ServiceResult:
        def _run(_: StepJobContext) -> StepJobOutcome:
            return StepJobOutcome(
                data={"mensagem": "Etapa contemplada na captura consolidada"},
                info_update={"summary": "Nenhuma ação necessária"},
            )

        return run_step_job(step=self.step, job_name=self.step, callback=_run)

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from xml.sax.saxutils import escape

from sirep import __version__
from sirep.app.captura import captura
from sirep.app.tratamento import tratamento
from sirep.domain.models import DiscardedPlan, Plan
from sirep.domain.schemas import DiscardedPlanOut, PlanOut
from sirep.infra.db import SessionLocal, init_db
from sirep.infra.logging import setup_logging
from sirep.services.notepad import build_notepad_txt
from sirep.infra.repositories import PlanLogRepository, TreatmentPlanRepository

logger = logging.getLogger(__name__)

setup_logging()        # <<< logs em arquivo + console
init_db()              # garante schema

app = FastAPI(title="SIREP 2.0", version=__version__)

ui_dir = Path(__file__).resolve().parent.parent / "ui"
app.mount("/app", StaticFiles(directory=str(ui_dir), html=True), name="ui")

try:
    DISPLAY_TZ = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:
    logger.warning(
        "Fuso horário 'America/Sao_Paulo' não encontrado; usando UTC como fallback"
    )
    DISPLAY_TZ = timezone.utc

CONTENT_TYPES_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">
  <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>
  <Default Extension=\"xml\" ContentType=\"application/xml\"/>
  <Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>
  <Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>
  <Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>
</Types>
"""

ROOT_RELS_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
  <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>
</Relationships>
"""

WORKBOOK_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">
  <sheets>
    <sheet name=\"Logs\" sheetId=\"1\" r:id=\"rId1\"/>
  </sheets>
</workbook>
"""

WORKBOOK_RELS_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
  <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>
  <Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>
</Relationships>
"""

STYLES_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">
  <fonts count=\"1\"><font><name val=\"Calibri\"/><family val=\"2\"/><sz val=\"11\"/></font></fonts>
  <fills count=\"1\"><fill><patternFill patternType=\"none\"/></fill></fills>
  <borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>
  <cellXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/></cellXfs>
  <cellStyles count=\"1\"><cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/></cellStyles>
</styleSheet>
"""


def _col_letter(idx: int) -> str:
    result = ""
    current = idx
    while current >= 0:
        current, remainder = divmod(current, 26)
        result = chr(ord("A") + remainder) + result
        current -= 1
    return result


def _format_datetime_local(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    value = dt
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        local = value.astimezone(DISPLAY_TZ)
    except Exception:
        local = value
    return local.strftime("%d/%m/%Y %H:%M:%S")


def _serialize_log(log) -> dict:
    created_at = log.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "id": log.id,
        "contexto": log.contexto,
        "treatment_id": log.treatment_id,
        "numero_plano": log.numero_plano,
        "etapa": log.etapa_numero,
        "etapa_nome": log.etapa_nome,
        "status": log.status,
        "mensagem": log.mensagem,
        "created_at": created_at.isoformat() if created_at else None,
    }


def _build_logs_sheet(rows: list[dict]) -> str:
    headers = ["Data e hora", "Plano", "Etapa", "Status", "Mensagem"]
    sheet_rows: list[str] = []
    header_cells = []
    for idx, title in enumerate(headers):
        col = _col_letter(idx)
        header_cells.append(
            f'<c r="{col}1" t="inlineStr"><is><t>{escape(title)}</t></is></c>'
        )
    sheet_rows.append(f'<row r="1">{"".join(header_cells)}</row>')

    for row_index, row in enumerate(rows, start=2):
        values = [
            row.get("created_at_display", ""),
            row.get("numero_plano") or "",
            row.get("etapa_nome") or "",
            row.get("status") or "",
            row.get("mensagem") or "",
        ]
        cells = []
        for col_idx, value in enumerate(values):
            col = _col_letter(col_idx)
            text = escape(str(value)) if value is not None else ""
            cells.append(
                f'<c r="{col}{row_index}" t="inlineStr"><is><t>{text}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    sheet_data = "".join(sheet_rows)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        f"<sheetData>{sheet_data}</sheetData>"
        "</worksheet>"
    )


def _build_logs_xlsx(rows: list[dict]) -> bytes:
    sheet_xml = _build_logs_sheet(rows)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", ROOT_RELS_XML)
        zf.writestr("xl/workbook.xml", WORKBOOK_XML)
        zf.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        zf.writestr("xl/styles.xml", STYLES_XML)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    buffer.seek(0)
    return buffer.getvalue()


def _intervalo_datetimes(
    data_inicial: Optional[date], data_final: Optional[date]
) -> tuple[Optional[datetime], Optional[datetime]]:
    if data_inicial is None or data_final is None:
        return None, None
    inicio_local = datetime.combine(data_inicial, time.min, tzinfo=DISPLAY_TZ)
    fim_local = datetime.combine(data_final, time.max, tzinfo=DISPLAY_TZ)
    return inicio_local.astimezone(timezone.utc), fim_local.astimezone(timezone.utc)

@app.get("/")
def root():
    return RedirectResponse(url="/app/")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/version")
def version():
    return {"version": __version__}

# ---- Handlers globais de erro ----
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    logger.warning("422 ValidationError %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.exception_handler(SQLAlchemyError)
async def sa_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("500 SQLAlchemyError %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "database error"})

@app.exception_handler(Exception)
async def default_handler(request: Request, exc: Exception):
    logger.exception("500 Unhandled %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error"})

# ---- Controle de captura ----
@app.post("/captura/iniciar")
async def captura_iniciar():
    captura.iniciar()
    return {"estado": captura.status().estado}

@app.post("/captura/pausar")
async def captura_pausar():
    captura.pausar()
    return {"estado": captura.status().estado}

@app.post("/captura/continuar")
async def captura_continuar():
    captura.continuar()
    return {"estado": captura.status().estado}

@app.get("/captura/status")
async def captura_status():
    st = captura.status()
    with SessionLocal() as db:
        ocorrencias_total = db.query(DiscardedPlan).count()
        total = db.query(Plan).count()
        total_passiveis = (
            db.query(Plan).filter(Plan.situacao_atual == "P. RESC").count()
        )
    progresso_total = captura.progresso_percentual()
    return {
        "estado": st.estado,
        "processados": st.processados,
        "novos": st.novos,
        "falhas": st.falhas,
        "progresso_total": progresso_total,
        "total_alvos": captura.total_alvos,
        "em_progresso": [
            {"numero_plano": p.numero_plano, "progresso": p.progresso, "etapas": p.etapas}
            for p in st.em_progresso.values()
        ],
        "historico": [
            {
                "numero_plano": h.numero_plano,
                "mensagem": h.mensagem,
                "progresso": h.progresso,
                "etapa": h.etapa,
                "etapa_nome": h.etapa_nome,
                "status": h.status,
                "timestamp": h.timestamp,
                "contexto": "gestao",
            }
            for h in st.historico
        ],
        "ultima_atualizacao": st.ultima_atualizacao,
        "ocorrencias_total": ocorrencias_total,
        "total": total,
        "total_passiveis": total_passiveis,
        "last_error": st.last_error,  # <<< surfaced
    }

@app.get("/captura/planos")
def captura_planos(pagina: int = 1, tamanho: int = 10):
    pagina = max(1, pagina)
    tamanho = max(1, min(tamanho, 100))

    with SessionLocal() as db:
        q = db.query(Plan).order_by(Plan.saldo.desc().nullslast())
        total = q.count()
        raw_items = q.offset((pagina - 1) * tamanho).limit(tamanho).all()
        items = [
            PlanOut.model_validate(plan).model_dump(mode="json")
            for plan in raw_items
        ]
        total_passiveis = (
            db.query(Plan).filter(Plan.situacao_atual == "P. RESC").count()
        )
        return {"items": items, "total": total, "total_passiveis": total_passiveis}

@app.get("/captura/ocorrencias")
def captura_ocorrencias(pagina: int = 1, tamanho: int = 10, situacao: str | None = None):
    pagina = max(1, pagina)
    tamanho = max(1, min(tamanho, 100))

    with SessionLocal() as db:
        q = db.query(DiscardedPlan).order_by(
            DiscardedPlan.saldo.desc().nullslast(),
            DiscardedPlan.id.desc(),
        )
        if situacao:
            value = situacao.strip()
            if value and value.upper() != "TODAS":
                q = q.filter(DiscardedPlan.situacao == value)
        total = q.count()
        raw_items = q.offset((pagina - 1) * tamanho).limit(tamanho).all()
        items = [
            DiscardedPlanOut.model_validate(plan).model_dump(mode="json")
            for plan in raw_items
        ]
        return {"items": items, "total": total}

# ---- Tratamentos ----

@app.post("/tratamentos/seed")
def tratamentos_seed(quantidade: int = 3):
    quantidade = max(1, min(quantidade, 10))
    ids = tratamento.seed_planos(quantidade)
    return {"criados": len(ids), "ids": ids}


@app.post("/tratamentos/migrar")
def tratamentos_migrar():
    ids = tratamento.migrar_planos()
    return {"criados": len(ids), "ids": ids}


@app.post("/tratamentos/iniciar")
def tratamentos_iniciar():
    tratamento.iniciar()
    return {"estado": tratamento.estado()}


@app.post("/tratamentos/pausar")
def tratamentos_pausar():
    tratamento.pausar()
    return {"estado": tratamento.estado()}


@app.post("/tratamentos/continuar")
def tratamentos_continuar():
    tratamento.continuar()
    return {"estado": tratamento.estado()}


@app.get("/tratamentos/status")
def tratamentos_status():
    return tratamento.status()


@app.get("/tratamentos/{treatment_id}/notepad")
def tratamentos_notepad(treatment_id: int):
    with SessionLocal() as db:
        repo = TreatmentPlanRepository(db)
        plano = repo.get(treatment_id)
        if plano is None:
            raise HTTPException(status_code=404, detail="Tratamento não encontrado")
        content = build_notepad_txt(plano.notas or {})
        filename = f"bloco_plano_{plano.numero_plano}.txt"
        response = PlainTextResponse(content, media_type="text/plain; charset=utf-8")
        response.headers["Content-Disposition"] = f"attachment; filename=\"{filename}\""
        return response


@app.get("/tratamentos/rescindidos-txt")
def tratamentos_rescindidos_txt(data: date):
    with SessionLocal() as db:
        repo = TreatmentPlanRepository(db)
        planos = repo.list_rescindidos_por_data(data)
        cnpjs: list[str] = []
        for plano in planos:
            for cnpj in plano.cnpjs:
                numero = re.sub(r"\D", "", cnpj)
                if numero:
                    cnpjs.append(numero)
        conteudo = ",".join(cnpjs)
        response = PlainTextResponse(conteudo, media_type="text/plain; charset=utf-8")
        response.headers["Content-Disposition"] = 'attachment; filename="Rescindidos_CNPJ.txt"'
        return response


@app.get("/logs")
def listar_logs(
    limit: int = 40,
    order: str = "desc",
    contexto: Optional[str] = None,
    data_inicial: Optional[date] = Query(None, alias="from"),
    data_final: Optional[date] = Query(None, alias="to"),
):
    ordem = order.lower()
    order_value = "asc" if ordem == "asc" else "desc"
    limite = max(1, min(limit, 200))
    inicio, fim = _intervalo_datetimes(data_inicial, data_final)

    with SessionLocal() as db:
        repo = PlanLogRepository(db)
        if inicio and fim:
            registros = repo.intervalo(inicio=inicio, fim=fim, contexto=contexto)
            if order_value == "desc":
                registros = list(reversed(registros))
            registros = registros[:limite]
        else:
            registros = repo.recentes(limit=limite, contexto=contexto, order=order_value)

    items = [_serialize_log(log) for log in registros]
    return {"items": items, "count": len(items)}


@app.get("/logs/export")
def exportar_logs(
    from_: date = Query(..., alias="from"),
    to: date = Query(..., alias="to"),
    contexto: Optional[str] = None,
):
    if from_ > to:
        raise HTTPException(status_code=400, detail="intervalo inválido")
    inicio, fim = _intervalo_datetimes(from_, to)
    if inicio is None or fim is None:
        raise HTTPException(status_code=400, detail="intervalo inválido")

    with SessionLocal() as db:
        repo = PlanLogRepository(db)
        registros = repo.intervalo(inicio=inicio, fim=fim, contexto=contexto)

    rows = []
    for log in registros:
        data = _serialize_log(log)
        data["created_at_display"] = _format_datetime_local(log.created_at)
        rows.append(data)

    content = _build_logs_xlsx(rows)
    stream = BytesIO(content)
    filename = f"logs_sirep_{from_.strftime('%Y%m%d')}_{to.strftime('%Y%m%d')}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"",
    }
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

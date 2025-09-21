from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from sirep import __version__
from sirep.app.captura import captura
from sirep.app.tratamento import tratamento
from sirep.domain.models import DiscardedPlan, Plan
from sirep.domain.schemas import DiscardedPlanOut, PlanOut
from sirep.infra.db import SessionLocal, init_db
from sirep.infra.logging import setup_logging
from sirep.services.notepad import build_notepad_txt
from sirep.infra.repositories import TreatmentPlanRepository

logger = logging.getLogger(__name__)

setup_logging()        # <<< logs em arquivo + console
init_db()              # garante schema

app = FastAPI(title="SIREP 2.0", version=__version__)

ui_dir = Path(__file__).resolve().parent.parent / "ui"
app.mount("/app", StaticFiles(directory=str(ui_dir), html=True), name="ui")

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
    db = SessionLocal()
    try:
        ocorrencias_total = db.query(DiscardedPlan).count()
        total = db.query(Plan).count()
        total_passiveis = db.query(Plan).filter(Plan.situacao_atual == "P. RESC").count()
    finally:
        db.close()
    return {
        "estado": st.estado,
        "processados": st.processados,
        "novos": st.novos,
        "falhas": st.falhas,
        "progresso_total": round((st.processados / 50) * 100, 1) if 50 else 0,
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
                "timestamp": h.timestamp,
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
    db = SessionLocal()
    try:
        q = db.query(Plan).order_by(Plan.saldo.desc().nullslast())
        total = q.count()
        raw_items = q.offset((pagina - 1) * tamanho).limit(tamanho).all()
        items = [
            PlanOut.model_validate(plan).model_dump(mode="json")
            for plan in raw_items
        ]
        total_passiveis = db.query(Plan).filter(Plan.situacao_atual == "P. RESC").count()
        return {"items": items, "total": total, "total_passiveis": total_passiveis}
    finally:
        db.close()

@app.get("/captura/ocorrencias")
def captura_ocorrencias(pagina: int = 1, tamanho: int = 10, situacao: str | None = None):
    db = SessionLocal()
    try:
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
    finally:
        db.close()

# ---- Tratamentos ----

@app.post("/tratamentos/seed")
def tratamentos_seed(quantidade: int = 3):
    quantidade = max(1, min(quantidade, 10))
    ids = tratamento.seed_planos(quantidade)
    return {"criados": len(ids), "ids": ids}


@app.post("/tratamentos/iniciar")
def tratamentos_iniciar():
    tratamento.iniciar()
    return {"estado": tratamento.estado()}


@app.get("/tratamentos/status")
def tratamentos_status():
    return tratamento.status()


@app.get("/tratamentos/{treatment_id}/notepad")
def tratamentos_notepad(treatment_id: int):
    db = SessionLocal()
    try:
        repo = TreatmentPlanRepository(db)
        plano = repo.get(treatment_id)
        if plano is None:
            raise HTTPException(status_code=404, detail="Tratamento não encontrado")
        content = build_notepad_txt(plano.notas or {})
        filename = f"bloco_plano_{plano.numero_plano}.txt"
        response = PlainTextResponse(content, media_type="text/plain; charset=utf-8")
        response.headers["Content-Disposition"] = f"attachment; filename=\"{filename}\""
        return response
    finally:
        db.close()


@app.get("/tratamentos/rescindidos-txt")
def tratamentos_rescindidos_txt(data: date):
    db = SessionLocal()
    try:
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
    finally:
        db.close()

# ---- Debug endpoint (força erro p/ validar logger) ----
@app.get("/debug/boom")
def boom():
    raise RuntimeError("boom de teste")
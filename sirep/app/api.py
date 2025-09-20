from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from sirep import __version__
from sirep.app.captura import captura
from sirep.domain.models import DiscardedPlan, Plan
from sirep.domain.schemas import DiscardedPlanOut, PlanOut
from sirep.infra.db import SessionLocal, init_db
from sirep.infra.logging import setup_logging

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
def captura_ocorrencias(pagina: int = 1, tamanho: int = 10):
    db = SessionLocal()
    try:
        q = db.query(DiscardedPlan).order_by(DiscardedPlan.id.desc())
        total = q.count()
        raw_items = q.offset((pagina - 1) * tamanho).limit(tamanho).all()
        items = [
            DiscardedPlanOut.model_validate(plan).model_dump(mode="json")
            for plan in raw_items
        ]
        return {"items": items, "total": total}
    finally:
        db.close()

# ---- Debug endpoint (força erro p/ validar logger) ----
@app.get("/debug/boom")
def boom():
    raise RuntimeError("boom de teste")
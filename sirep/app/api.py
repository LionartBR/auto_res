from fastapi import FastAPI, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
from datetime import datetime
from sirep import __version__
from sirep.infra.db import init_db, SessionLocal
from sirep.domain.models import Plan, Event, DiscardedPlan
from sirep.app.captura import captura

app = FastAPI(title="SIREP 2.0", version=__version__)
init_db()
app.mount("/app", StaticFiles(directory="ui", html=True), name="ui")

@app.get("/")
def root(): return RedirectResponse(url="/app/")

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/version")
def version(): return {"version": __version__}

# Controle
@app.post("/captura/iniciar")
async def captura_iniciar(): captura.iniciar(); return {"estado": captura.status().estado}
@app.post("/captura/pausar")
async def captura_pausar(): captura.pausar(); return {"estado": captura.status().estado}
@app.post("/captura/continuar")
async def captura_continuar(): captura.continuar(); return {"estado": captura.status().estado}

@app.get("/captura/status")
async def captura_status():
    st = captura.status()
    total_previsto = 50
    perc = round((st.processados / total_previsto) * 100, 1) if total_previsto else 0.0
    # contador de ocorrências
    db = SessionLocal()
    try:
        ocorrencias_total = db.query(DiscardedPlan).count()
    finally:
        db.close()
    return {
        "estado": st.estado, "processados": st.processados, "novos": st.novos, "falhas": st.falhas,
        "progresso_total": perc,
        "em_progresso": [{"numero_plano": p.numero_plano, "progresso": p.progresso, "etapas": p.etapas} for p in st.em_progresso.values()],
        "ultima_atualizacao": st.ultima_atualizacao,
        "ocorrencias_total": ocorrencias_total,
    }

# Dados: Planos capturados (com total e total_passiveis)
@app.get("/captura/planos")
def captura_planos(pagina: int = Query(1, ge=1), tamanho: int = Query(10, ge=1, le=200), desde: Optional[str] = None):
    db = SessionLocal()
    try:
        q = db.query(Plan)
        if desde:
            try:
                dt = datetime.fromisoformat(desde.replace("Z",""))
                q = q.filter(Plan.updated_at >= dt)
            except Exception:
                ...
        total = q.count()
        total_passiveis = q.filter(Plan.situacao_atual == "P. RESC").count()
        items = q.order_by(Plan.saldo.desc().nullslast()).offset((pagina-1)*tamanho).limit(tamanho).all()
        return {"items": items, "total": total, "total_passiveis": total_passiveis}
    finally:
        db.close()

# Dados: Ocorrências (descartados)
@app.get("/captura/ocorrencias")
def captura_ocorrencias(pagina: int = Query(1, ge=1), tamanho: int = Query(10, ge=1, le=200)):
    db = SessionLocal()
    try:
        q = db.query(DiscardedPlan)
        total = q.count()
        rows = q.order_by(DiscardedPlan.id.desc()).offset((pagina-1)*tamanho).limit(tamanho).all()
        return {"items": rows, "total": total}
    finally:
        db.close()
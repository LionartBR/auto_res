from __future__ import annotations
from datetime import date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Float,
    func,
    ForeignKey,
    JSON,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True, autoincrement=True)
    numero_plano = Column(String(32), unique=True, index=True, nullable=False)
    gifug = Column(String(8), nullable=True)
    razao_social = Column(String(255), nullable=True)
    situacao_atual = Column(String(32), nullable=True)
    situacao_anterior = Column(String(32), nullable=True)
    dias_em_atraso = Column(Integer, nullable=True)
    tipo = Column(String(8), nullable=True)
    dt_situacao_atual = Column(Date, nullable=True)
    saldo = Column(Float, nullable=True)
    cmb_ajuste = Column(String(64), nullable=True)
    justificativa = Column(String(255), nullable=True)
    matricula = Column(String(64), nullable=True)
    dt_parcela_atraso = Column(Date, nullable=True)
    representacao = Column(String(64), nullable=True)
    tipo_parcelamento = Column(String(8), nullable=True)
    saldo_total = Column(Float, nullable=True)
    status = Column(String(16), nullable=True)
    data_rescisao = Column(Date, nullable=True)
    data_comunicacao = Column(Date, nullable=True)
    metodo_comunicacao = Column(String(16), nullable=True)
    referencia_comunicacao = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    step = Column(String(64), nullable=False)
    message = Column(String(255), nullable=False)
    level = Column(String(16), nullable=False, default="INFO")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class JobRun(Base):
    __tablename__ = "job_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(64), nullable=False)              # obrigatório
    step = Column(String(64), nullable=True)                   # novo
    input_hash = Column(String(128), nullable=True)            # novo
    info = Column(JSON, nullable=True)  # novo (JSON storage)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False, default="OK")  # OK | FAIL | RUNNING etc.

class DiscardedPlan(Base):
    __tablename__ = "discarded_plans"
    id = Column(Integer, primary_key=True, autoincrement=True)
    numero_plano = Column(String(32), nullable=False, index=True)
    situacao = Column(String(32), nullable=False)
    cnpj = Column(String(18), nullable=False)
    tipo = Column(String(8), nullable=True)
    saldo = Column(Float, nullable=True)
    dt_situacao_atual = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TreatmentPlan(Base):
    __tablename__ = "treatment_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    numero_plano = Column(String(32), nullable=False, index=True)
    razao_social = Column(String(255), nullable=False)
    status = Column(String(16), nullable=False, default="pendente")
    etapa_atual = Column(Integer, nullable=False, default=0)
    periodo = Column(String(64), nullable=True)
    cnpjs = Column(MutableList.as_mutable(JSON), nullable=False, default=list)
    notas = Column(MutableDict.as_mutable(JSON), nullable=False, default=dict)
    etapas = Column(MutableList.as_mutable(JSON), nullable=False, default=list)
    bases = Column(MutableList.as_mutable(JSON), nullable=False, default=list)
    rescisao_data = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
class PlanLog(Base):
    __tablename__ = "plan_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contexto = Column(String(32), nullable=False, index=True)
    numero_plano = Column(String(32), nullable=True, index=True)
    treatment_id = Column(Integer, ForeignKey("treatment_plans.id"), nullable=True, index=True)
    etapa_numero = Column(Integer, nullable=True)
    etapa_nome = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False)
    mensagem = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
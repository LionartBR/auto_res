from __future__ import annotations
from datetime import date
from sqlalchemy import Column, Integer, String, Date, DateTime, Float, func, ForeignKey, JSON, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True, autoincrement=True)
    numero_plano = Column(String(32), unique=True, index=True, nullable=False)
    gifug = Column(String(8), nullable=True)
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
    status = Column(String(16), nullable=True)  # requerido pelo upsert
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
    info = Column(JSON().with_variant(Text, "sqlite"), nullable=True)  # novo (TEXT no SQLite)
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
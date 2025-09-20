from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from .enums import PlanStatus, Step

class PlanIn(BaseModel):
    numero_plano: str
    gifug: Optional[str] = None
    situacao_atual: Optional[str] = None
    situacao_anterior: Optional[str] = None
    dias_em_atraso: Optional[int] = None
    tipo: Optional[str] = None
    dt_situacao_atual: Optional[date] = None
    saldo: Optional[float] = None
    cmb_ajuste: Optional[str] = None
    justificativa: Optional[str] = None
    matricula: Optional[str] = None
    dt_parcela_atraso: Optional[date] = None
    representacao: Optional[str] = None

class PlanOut(BaseModel):
    id: int
    numero_plano: str
    gifug: Optional[str] = None
    situacao_atual: Optional[str] = None
    situacao_anterior: Optional[str] = None
    dias_em_atraso: Optional[int] = None
    tipo: Optional[str] = None
    dt_situacao_atual: Optional[date] = None
    saldo: Optional[float] = None
    cmb_ajuste: Optional[str] = None
    justificativa: Optional[str] = None
    matricula: Optional[str] = None
    dt_parcela_atraso: Optional[date] = None
    representacao: Optional[str] = None
    status: PlanStatus

    class Config:
        from_attributes = True


class DiscardedPlanOut(BaseModel):
    id: int
    numero_plano: str
    situacao: str
    cnpj: str
    tipo: Optional[str] = None
    saldo: Optional[float] = None
    dt_situacao_atual: Optional[date] = None
    created_at: datetime

    class Config:
        from_attributes = True

class JobRequest(BaseModel):
    steps: List[Step]

class JobStatus(BaseModel):
    job_id: int
    status: str
    step: Step
    started_at: datetime
    finished_at: Optional[datetime] = None
    info: Optional[str] = None

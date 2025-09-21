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
    data_rescisao: Optional[date] = None
    data_comunicacao: Optional[date] = None
    metodo_comunicacao: Optional[str] = None
    referencia_comunicacao: Optional[str] = None

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


class TreatmentStageOut(BaseModel):
    id: int
    nome: str
    status: str
    iniciado_em: Optional[datetime] = None
    finalizado_em: Optional[datetime] = None
    mensagem: Optional[str] = None


class TreatmentPlanOut(BaseModel):
    id: int
    plan_id: int
    numero_plano: str
    razao_social: str
    status: str
    etapa_atual: int
    periodo: Optional[str] = None
    cnpjs: List[str]
    bases: List[str]
    rescisao_data: Optional[date] = None
    etapas: List[TreatmentStageOut]

    class Config:
        from_attributes = True


class TreatmentLogOut(BaseModel):
    id: int
    treatment_id: int
    etapa: int
    status: str
    mensagem: str
    created_at: datetime

    class Config:
        from_attributes = True

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel

from .enums import PlanStatus

class PlanOut(BaseModel):
    id: int
    numero_plano: str
    gifug: Optional[str] = None
    razao_social: Optional[str] = None
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
    cnpj: Optional[str] = None
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


class StepMetadataOut(BaseModel):
    code: str
    label: str
    category: str
    order: int
    stage: Optional[int] = None


class PipelineRunRequest(BaseModel):
    steps: Optional[list[str]] = None


class PipelineRunItem(BaseModel):
    code: str
    label: str
    category: str
    order: int
    result: dict[str, Any]
    stage: Optional[int] = None


class PipelineRunResponse(BaseModel):
    count: int
    items: list[PipelineRunItem]


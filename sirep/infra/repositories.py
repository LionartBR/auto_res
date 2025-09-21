from datetime import datetime, timezone
from datetime import date
from typing import Optional, Sequence, Any, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from sirep.domain.models import (
    Plan,
    Event,
    JobRun,
    DiscardedPlan,
    TreatmentPlan,
    PlanLog,
)
from sirep.domain.enums import PlanStatus, Step

class PlanRepository:
    def __init__(self, db: Session): self.db = db
    def get_by_numero(self, numero_plano: str) -> Optional[Plan]:
        return self.db.scalar(select(Plan).where(Plan.numero_plano==numero_plano))
    def upsert(self, numero_plano: str, **fields) -> Plan:
        plan = self.get_by_numero(numero_plano)
        if not plan:
            plan = Plan(numero_plano=numero_plano, **fields)
            self.db.add(plan)
        else:
            for k,v in fields.items(): setattr(plan, k, v)
        self.db.flush()
        return plan
    def list_by_status(self, status: PlanStatus) -> Sequence[Plan]:
        return self.db.scalars(select(Plan).where(Plan.status==status)).all()
    def set_status(self, plan: Plan, status: PlanStatus): plan.status = status

class EventRepository:
    def __init__(self, db: Session): self.db = db
    def log(self, plan_id: int, step: Step, message: str, level: str="INFO"):
        self.db.add(Event(plan_id=plan_id, step=step, message=message, level=level))

class JobRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def start(
        self,
        *,
        job_name: str,
        step: Optional[str] = None,
        input_hash: Optional[str] = None,
        info: Optional[Dict[str, Any]] = None,
        status: str = "RUNNING",
    ) -> JobRun:
        """Cria um JobRun com os campos esperados pelo pipeline."""
        jr = JobRun(
            job_name=job_name,
            step=step,
            input_hash=input_hash,
            info=info,
            status=status,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(jr)
        self.db.flush()  # garante jr.id
        return jr

    def finish(
        self,
        job_run_id: int,
        *,
        status: str = "OK",
        info_update: Optional[Dict[str, Any]] = None,
    ) -> JobRun:
        jr = self.db.query(JobRun).filter(JobRun.id == job_run_id).one()
        jr.status = status
        jr.finished_at = datetime.now(timezone.utc)
        if info_update:
            # mescla info antiga com update simples (dict shallow)
            merged = dict(jr.info or {})
            merged.update(info_update)
            jr.info = merged
        self.db.add(jr)
        return jr

    def fail(self, job_run_id: int, *, info_update: Optional[Dict[str, Any]] = None) -> JobRun:
        return self.finish(job_run_id, status="FAIL", info_update=info_update)

class OccurrenceRepository:
    def __init__(self, db: Session): self.db = db

    def add(self, *, numero_plano: str, situacao: str, cnpj: str, tipo: str, saldo: float, dt_situacao_atual):
        row = DiscardedPlan(
            numero_plano=numero_plano, situacao=situacao, cnpj=cnpj,
            tipo=tipo, saldo=saldo, dt_situacao_atual=dt_situacao_atual
        )
        self.db.add(row)
        return row

    def paginate(self, *, pagina: int, tamanho: int):
        q = self.db.query(DiscardedPlan).order_by(DiscardedPlan.id.desc())
        total = q.count()
        rows = q.offset((pagina-1)*tamanho).limit(tamanho).all()
        return rows, total


class TreatmentPlanRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> List[TreatmentPlan]:
        stmt = select(TreatmentPlan).order_by(TreatmentPlan.id.asc())
        return list(self.db.scalars(stmt))

    def get(self, treatment_id: int) -> Optional[TreatmentPlan]:
        return self.db.scalar(select(TreatmentPlan).where(TreatmentPlan.id == treatment_id))

    def by_plan_id(self, plan_id: int) -> Optional[TreatmentPlan]:
        return self.db.scalar(select(TreatmentPlan).where(TreatmentPlan.plan_id == plan_id))

    def add(self, plan: TreatmentPlan) -> TreatmentPlan:
        self.db.add(plan)
        self.db.flush()
        return plan

    def remove(self, plan: TreatmentPlan) -> None:
        self.db.delete(plan)

    def list_rescindidos_por_data(self, data: date) -> List[TreatmentPlan]:
        stmt = select(TreatmentPlan).where(
            TreatmentPlan.status == "rescindido",
            TreatmentPlan.rescisao_data == data,
        )
        return list(self.db.scalars(stmt))


class PlanLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(
        self,
        *,
        contexto: str,
        status: str,
        mensagem: str,
        numero_plano: Optional[str] = None,
        etapa_numero: Optional[int] = None,
        etapa_nome: Optional[str] = None,
        treatment_id: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ) -> PlanLog:
        contexto_norm = (contexto or "").strip().lower() or "geral"
        status_norm = (status or "").strip().upper() or "INFO"
        row = PlanLog(
            contexto=contexto_norm,
            status=status_norm,
            mensagem=mensagem,
            numero_plano=numero_plano,
            etapa_numero=etapa_numero,
            etapa_nome=etapa_nome,
            treatment_id=treatment_id,
        )
        if created_at is not None:
            row.created_at = created_at
        self.db.add(row)
        self.db.flush()
        return row

    def recentes(
        self,
        *,
        limit: int = 20,
        contexto: Optional[str] = None,
        order: str = "desc",
    ) -> List[PlanLog]:
        stmt = select(PlanLog)
        if contexto:
            stmt = stmt.where(PlanLog.contexto == contexto)
        if order == "asc":
            stmt = stmt.order_by(PlanLog.created_at.asc(), PlanLog.id.asc())
        else:
            stmt = stmt.order_by(PlanLog.created_at.desc(), PlanLog.id.desc())
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt))

    def intervalo(
        self,
        *,
        inicio: datetime,
        fim: datetime,
        contexto: Optional[str] = None,
    ) -> List[PlanLog]:
        stmt = select(PlanLog).where(
            PlanLog.created_at >= inicio,
            PlanLog.created_at <= fim,
        )
        if contexto:
            stmt = stmt.where(PlanLog.contexto == contexto)
        stmt = stmt.order_by(PlanLog.created_at.asc(), PlanLog.id.asc())
        return list(self.db.scalars(stmt))
"""Repository layer abstractions to interact with persistence models."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sirep.domain.enums import PlanStatus, Step
from sirep.domain.models import (
    DiscardedPlan,
    Event,
    JobRun,
    Plan,
    PlanLog,
    TreatmentPlan,
)


class PlanRepository:
    """Persistence helpers for :class:`Plan` entities."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_numero(self, numero_plano: str) -> Optional[Plan]:
        stmt = select(Plan).where(Plan.numero_plano == numero_plano)
        return self._db.scalar(stmt)

    def upsert(self, numero_plano: str, **fields: Any) -> Plan:
        plan = self.get_by_numero(numero_plano)
        if plan is None:
            plan = Plan(numero_plano=numero_plano, **fields)
            self._db.add(plan)
        else:
            for key, value in fields.items():
                setattr(plan, key, value)
        self._db.flush([plan])
        return plan

    def list_by_status(self, status: PlanStatus | str) -> list[Plan]:
        target_status = status.value if isinstance(status, PlanStatus) else str(status)
        stmt = select(Plan).where(Plan.status == target_status)
        return list(self._db.scalars(stmt))

    def list_all(self) -> list[Plan]:
        stmt = select(Plan).order_by(Plan.id.asc())
        return list(self._db.scalars(stmt))

    def set_status(self, plan: Plan, status: PlanStatus | str) -> None:
        plan.status = status.value if isinstance(status, PlanStatus) else str(status)
        self._db.flush([plan])


class EventRepository:
    """Utility to store events emitted during processing."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def log(self, plan_id: int, step: Step, message: str, level: str = "INFO") -> Event:
        event = Event(plan_id=plan_id, step=step, message=message, level=level)
        self._db.add(event)
        self._db.flush([event])
        return event


class JobRunRepository:
    """Manage job execution metadata stored in ``job_runs`` table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def start(
        self,
        *,
        job_name: str,
        step: Optional[str] = None,
        input_hash: Optional[str] = None,
        info: Optional[Dict[str, Any]] = None,
        status: str = "RUNNING",
    ) -> JobRun:
        job_run = JobRun(
            job_name=job_name,
            step=step,
            input_hash=input_hash,
            info=info,
            status=status,
            started_at=datetime.now(timezone.utc),
        )
        self._db.add(job_run)
        self._db.flush([job_run])
        return job_run

    def finish(
        self,
        job_run_id: int,
        *,
        status: str = "OK",
        info_update: Optional[Dict[str, Any]] = None,
    ) -> JobRun:
        job_run = self._db.get(JobRun, job_run_id)
        if job_run is None:
            raise ValueError(f"JobRun com id={job_run_id} não encontrado")

        job_run.status = status
        job_run.finished_at = datetime.now(timezone.utc)

        if info_update:
            merged = dict(job_run.info or {})
            merged.update(info_update)
            job_run.info = merged

        self._db.flush([job_run])
        return job_run

    def fail(
        self, job_run_id: int, *, info_update: Optional[Dict[str, Any]] = None
    ) -> JobRun:
        return self.finish(job_run_id, status="FAIL", info_update=info_update)


class OccurrenceRepository:
    """Persist occurrences of discarded plans."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_all(self) -> list[DiscardedPlan]:
        stmt = select(DiscardedPlan).order_by(DiscardedPlan.id.asc())
        return list(self._db.scalars(stmt))

    def add(
        self,
        *,
        numero_plano: str,
        situacao: str,
        cnpj: str,
        tipo: Optional[str] = None,
        saldo: Optional[float] = None,
        dt_situacao_atual: Optional[date] = None,
    ) -> DiscardedPlan:
        row = DiscardedPlan(
            numero_plano=numero_plano,
            situacao=situacao,
            cnpj=cnpj,
            tipo=tipo,
            saldo=saldo,
            dt_situacao_atual=dt_situacao_atual,
        )
        self._db.add(row)
        self._db.flush([row])
        return row

    def paginate(self, *, pagina: int, tamanho: int) -> tuple[list[DiscardedPlan], int]:
        stmt = (
            select(DiscardedPlan)
            .order_by(DiscardedPlan.id.desc())
            .offset((pagina - 1) * tamanho)
            .limit(tamanho)
        )
        rows = list(self._db.scalars(stmt))
        total = self._db.scalar(select(func.count()).select_from(DiscardedPlan)) or 0
        return rows, int(total)


class TreatmentPlanRepository:
    """Handle persistence of treatment plans."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_all(self) -> list[TreatmentPlan]:
        stmt = select(TreatmentPlan).order_by(TreatmentPlan.id.asc())
        return list(self._db.scalars(stmt))

    def get(self, treatment_id: int) -> Optional[TreatmentPlan]:
        stmt = select(TreatmentPlan).where(TreatmentPlan.id == treatment_id)
        return self._db.scalar(stmt)

    def by_plan_id(self, plan_id: int) -> Optional[TreatmentPlan]:
        stmt = select(TreatmentPlan).where(TreatmentPlan.plan_id == plan_id)
        return self._db.scalar(stmt)

    def add(self, plan: TreatmentPlan) -> TreatmentPlan:
        self._db.add(plan)
        self._db.flush([plan])
        return plan

    def remove(self, plan: TreatmentPlan) -> None:
        self._db.delete(plan)

    def list_rescindidos_por_periodo(self, inicio: date, fim: date) -> list[TreatmentPlan]:
        stmt = (
            select(TreatmentPlan)
            .where(
                TreatmentPlan.status == "rescindido",
                TreatmentPlan.rescisao_data >= inicio,
                TreatmentPlan.rescisao_data <= fim,
            )
            .order_by(TreatmentPlan.rescisao_data.asc(), TreatmentPlan.id.asc())
        )
        return list(self._db.scalars(stmt))


class PlanLogRepository:
    """Accessors for plan log records."""

    def __init__(self, db: Session) -> None:
        self._db = db

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
        contexto_norm = self._normalize_context(contexto)
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
        self._db.add(row)
        self._db.flush([row])
        return row

    def recentes(
        self,
        *,
        limit: int = 20,
        contexto: Optional[str] = None,
        order: str = "desc",
    ) -> list[PlanLog]:
        stmt = select(PlanLog)
        if contexto:
            stmt = stmt.where(PlanLog.contexto == self._normalize_context(contexto))
        if order == "asc":
            stmt = stmt.order_by(PlanLog.created_at.asc(), PlanLog.id.asc())
        else:
            stmt = stmt.order_by(PlanLog.created_at.desc(), PlanLog.id.desc())
        if limit:
            stmt = stmt.limit(limit)
        return list(self._db.scalars(stmt))

    def intervalo(
        self,
        *,
        inicio: datetime,
        fim: datetime,
        contexto: Optional[str] = None,
    ) -> list[PlanLog]:
        stmt = select(PlanLog).where(
            PlanLog.created_at >= inicio,
            PlanLog.created_at <= fim,
        )
        if contexto:
            stmt = stmt.where(PlanLog.contexto == self._normalize_context(contexto))
        stmt = stmt.order_by(PlanLog.created_at.asc(), PlanLog.id.asc())
        return list(self._db.scalars(stmt))

    @staticmethod
    def _normalize_context(value: Optional[str]) -> str:
        return (value or "").strip().lower() or "geral"


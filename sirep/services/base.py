from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol, Union

from sqlalchemy.orm import Session

from sirep.domain.enums import Step
from sirep.domain.models import JobRun
from sirep.infra.db import SessionLocal
from sirep.infra.repositories import EventRepository, JobRunRepository, PlanRepository

@contextmanager
def unit_of_work():
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

class ServiceResult(Dict[str, Any]):
    """Convenience mapping used by service layer helpers."""


@dataclass
class StepJobOutcome:
    """Result returned by callbacks executed via :func:`run_step_job`."""

    data: Optional[Dict[str, Any]] = None
    status: str = "FINISHED"
    info_update: Optional[Dict[str, Any]] = None


@dataclass
class StepJobContext:
    """Context shared with step execution callbacks."""

    db: Session
    plans: PlanRepository
    events: EventRepository
    jobs: JobRunRepository
    step: Step
    job: Optional[JobRun] = None


class StepJobCallback(Protocol):
    def __call__(self, ctx: "StepJobContext") -> Union[StepJobOutcome, Dict[str, Any], None]:
        """Execute the step-specific logic using the provided repositories."""


def run_step_job(
    *,
    step: Step,
    callback: StepJobCallback,
    job_name: Optional[str] = None,
    input_hash: Union[str, Callable[["StepJobContext"], str], None] = None,
) -> ServiceResult:
    """Execute a step job with shared boilerplate encapsulated.

    Parameters
    ----------
    step:
        Step being executed. Also used as default job name.
    callback:
        Function containing the specific logic for the step. It receives a
        :class:`StepJobContext` with repositories and must return either a
        :class:`StepJobOutcome`, a plain mapping with the result payload or
        ``None``.
    job_name:
        Optional explicit name for the job. Defaults to ``step``.
    input_hash:
        Optional pre-computed hash or callable that receives a context (without
        an active job) and returns the hash. Useful for hashing inputs fetched
        from the database before starting the job.
    """

    with unit_of_work() as db:
        plans = PlanRepository(db)
        events = EventRepository(db)
        jobs = JobRunRepository(db)
        context = StepJobContext(db=db, plans=plans, events=events, jobs=jobs, step=step)

        resolved_hash: Optional[str]
        if callable(input_hash):
            resolved_hash = input_hash(context)
        else:
            resolved_hash = input_hash

        resolved_job_name = job_name.name if isinstance(job_name, Step) else job_name
        default_job_name = step.name if isinstance(step, Step) else str(step)
        job = jobs.start(
            job_name=resolved_job_name or default_job_name,
            step=step,
            input_hash=resolved_hash,
        )
        context.job = job

        outcome = callback(context)
        if isinstance(outcome, StepJobOutcome):
            payload = ServiceResult(outcome.data or {})
            status = outcome.status
            info_update = outcome.info_update
        else:
            payload = ServiceResult(outcome or {})  # type: ignore[arg-type]
            status = "FINISHED"
            info_update = None

        jobs.finish(job.id, status=status, info_update=info_update)
        payload["job_id"] = job.id
        return payload
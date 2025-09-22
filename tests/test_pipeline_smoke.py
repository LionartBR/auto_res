import pytest

from sirep.domain.enums import PlanStatus, Step
from sirep.domain.models import JobRun
from sirep.infra.db import SessionLocal, init_db
from sirep.infra.repositories import JobRunRepository
from sirep.services.base import StepJobOutcome, run_step_job

@pytest.fixture(scope="module", autouse=True)
def _setup_schema():
    # garante schema criado
    init_db()

def test_jobrun_start_and_finish():
    with SessionLocal() as db:
        repo = JobRunRepository(db)
        jr = repo.start(job_name="captura", step="ETAPA_1", input_hash="abc123", info={"a":1})
        assert jr.id is not None
        assert jr.job_name == "captura"
        assert jr.step == "ETAPA_1"
        assert jr.status == "RUNNING"
        db.commit()

    with SessionLocal() as db:
        repo = JobRunRepository(db)
        jr2 = repo.finish(jr.id, status="OK", info_update={"b":2})
        db.commit()
    assert jr2.status == "OK"


def test_run_step_job_helper_executes_callback():
    numero = "HELPER001"

    def _callback(ctx) -> StepJobOutcome:
        plan = ctx.plans.upsert(numero, status=PlanStatus.NOVO)
        ctx.events.log(plan.id, Step.ETAPA_1, "execucao helper")
        return StepJobOutcome(
            data={"numero": plan.numero_plano},
            info_update={"summary": "done"},
        )

    result = run_step_job(
        step=Step.ETAPA_1,
        job_name="helper",
        input_hash="hash-123",
        callback=_callback,
    )

    assert result["job_id"] > 0
    assert result["numero"] == numero

    with SessionLocal() as db:
        job = db.get(JobRun, result["job_id"])
        assert job is not None
        assert job.status == "FINISHED"
        assert job.job_name == "helper"
        assert job.step == Step.ETAPA_1
        assert job.input_hash == "hash-123"
        assert job.info is not None and job.info.get("summary") == "done"
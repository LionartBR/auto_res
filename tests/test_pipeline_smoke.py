import os
import pytest
from sirep.infra.db import SessionLocal, init_db
from sirep.infra.repositories import JobRunRepository

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
import pytest
from fastapi.testclient import TestClient

from sirep.app.api import app
from sirep.domain.models import JobRun, Plan
from sirep.infra.db import SessionLocal, init_db


@pytest.fixture
def client():
    init_db()
    with SessionLocal() as db:
        db.query(JobRun).delete()
        db.query(Plan).delete()
        db.commit()
    with TestClient(app) as test_client:
        yield test_client


def test_pipeline_steps_endpoint(client: TestClient):
    response = client.get("/pipeline/steps")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert payload["count"] == len(payload["items"])
    assert any(item["code"] == "ETAPA_1" for item in payload["items"])


def test_pipeline_run_selected_steps(client: TestClient):
    response = client.post("/pipeline/run", json={"steps": ["ETAPA_1", "ETAPA_2"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    codes = [item["code"] for item in payload["items"]]
    assert codes == ["ETAPA_1", "ETAPA_2"]
    for item in payload["items"]:
        assert isinstance(item["result"], dict)
        assert "job_id" in item["result"]

    with SessionLocal() as db:
        jobs = db.query(JobRun).order_by(JobRun.id.asc()).all()
        assert len(jobs) == 2
        assert [job.job_name for job in jobs] == ["ETAPA_1", "ETAPA_2"]
        plans = db.query(Plan).all()
        assert plans, "Etapa 1 deveria criar planos na base"


def test_pipeline_run_invalid_step(client: TestClient):
    response = client.post("/pipeline/run", json={"steps": ["INVALIDA"]})
    assert response.status_code == 400
    detail = response.json().get("detail")
    assert "Etapa inválida" in detail

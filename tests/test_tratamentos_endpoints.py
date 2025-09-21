import pytest
from fastapi.testclient import TestClient
from datetime import date

from sirep.app.api import app
from sirep.domain.enums import PlanStatus
from sirep.domain.models import Plan, TreatmentPlan
from sirep.infra.db import SessionLocal, init_db


@pytest.fixture
def client():
    init_db()
    with SessionLocal() as db:
        db.query(TreatmentPlan).delete()
        db.query(Plan).delete()
        db.commit()
    with TestClient(app) as test_client:
        yield test_client


def test_migrar_tratamentos(client: TestClient):
    with SessionLocal() as db:
        plano = Plan(
            numero_plano="123456",
            situacao_atual="P. RESC",
            saldo=5000.0,
            status=PlanStatus.PASSIVEL_RESC,
            razao_social="EMPRESA ALFA LTDA",
            tipo="ADM",
        )
        db.add(plano)
        db.commit()

    response = client.post("/tratamentos/migrar")
    assert response.status_code == 200
    payload = response.json()
    assert payload["criados"] == 1
    assert isinstance(payload["ids"], list)
    assert payload["ids"]

    status = client.get("/tratamentos/status")
    assert status.status_code == 200
    body = status.json()
    assert "planos" in body
    assert isinstance(body["planos"], list)
    assert body["planos"]
    first = body["planos"][0]
    assert "numero_plano" in first
    assert "etapas" in first
    assert first["razao_social"] == "EMPRESA ALFA LTDA"


def test_tratamento_notepad_endpoint(client: TestClient):
    with SessionLocal() as db:
        plano = Plan(
            numero_plano="654321",
            situacao_atual="P. RESC",
            saldo=4200.0,
            status=PlanStatus.PASSIVEL_RESC,
            razao_social="EMPRESA BETA LTDA",
            tipo="INS",
        )
        db.add(plano)
        db.commit()

    client.post("/tratamentos/migrar")
    status = client.get("/tratamentos/status").json()
    plan_id = status["planos"][0]["id"]

    response = client.get(f"/tratamentos/{plan_id}/notepad")
    assert response.status_code == 200
    assert "DEPURAÇÃO PARCELAMENTO" in response.text
    assert "Content-Disposition" in response.headers


def test_rescindidos_txt_endpoint(client: TestClient):
    hoje = date.today()
    with SessionLocal() as db:
        plano = Plan(
            numero_plano="900001",
            situacao_atual="RESCINDIDO",
            saldo=100.0,
            status=PlanStatus.RESCINDIDO,
            data_rescisao=hoje,
            razao_social="EMPRESA TESTE LTDA",
        )
        db.add(plano)
        db.flush()

        tratamento = TreatmentPlan(
            plan_id=plano.id,
            numero_plano=plano.numero_plano,
            razao_social="EMPRESA TESTE LTDA",
            status="rescindido",
            etapa_atual=7,
            periodo="01/2020 a 12/2020",
            cnpjs=["12.345.678/0001-90", "98.765.432/0001-09"],
            notas={},
            etapas=[],
            bases=["RJ", "SP"],
            rescisao_data=hoje,
        )
        db.add(tratamento)
        db.commit()

    response = client.get(f"/tratamentos/rescindidos-txt?data={hoje.isoformat()}")
    assert response.status_code == 200
    body = response.text
    assert "12345678000190" in body
    assert "98765432000109" in body
    assert response.headers.get("content-disposition", "").startswith("attachment")

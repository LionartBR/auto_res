from datetime import date

import pytest
from fastapi.testclient import TestClient

from sirep.app.api import app
from sirep.domain.models import DiscardedPlan, Plan
from sirep.infra.db import SessionLocal, init_db


@pytest.fixture
def client_with_data():
    init_db()
    with SessionLocal() as db:
        db.query(DiscardedPlan).delete()
        db.query(Plan).delete()
        db.commit()

        plan = Plan(
            numero_plano="0001",
            situacao_atual="P. RESC",
            saldo=123.45,
            status="NOVO",
        )
        db.add(plan)

        discarded = DiscardedPlan(
            numero_plano="0002",
            situacao="ERRO_PROCESSAMENTO",
            cnpj="12.345.678/0001-90",
            tipo="TESTE",
            saldo=67.89,
            dt_situacao_atual=date(2023, 1, 1),
        )
        db.add(discarded)
        db.commit()

    with TestClient(app) as client:
        yield client


def test_captura_planos_returns_serializable(client_with_data):
    response = client_with_data.get("/captura/planos")
    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 1
    assert payload["total_passiveis"] == 1
    assert payload["items"]
    first = payload["items"][0]
    assert first["numero_plano"] == "0001"
    assert first["status"] == "NOVO"


def test_captura_ocorrencias_returns_serializable(client_with_data):
    response = client_with_data.get("/captura/ocorrencias")
    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 1
    assert payload["items"]
    first = payload["items"][0]
    assert first["numero_plano"] == "0002"
    assert first["situacao"] == "ERRO_PROCESSAMENTO"

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

        discarded_high = DiscardedPlan(
            numero_plano="0003",
            situacao="ERRO_PROCESSAMENTO",
            cnpj="23.456.789/0001-01",
            tipo="TESTE",
            saldo=250.0,
            dt_situacao_atual=date(2023, 1, 2),
        )
        discarded_mid = DiscardedPlan(
            numero_plano="0002",
            situacao="ERRO_PROCESSAMENTO",
            cnpj="12.345.678/0001-90",
            tipo="TESTE",
            saldo=67.89,
            dt_situacao_atual=date(2023, 1, 1),
        )
        discarded_none = DiscardedPlan(
            numero_plano="0004",
            situacao="ERRO_PROCESSAMENTO",
            cnpj="34.567.890/0001-12",
            tipo="TESTE",
            saldo=None,
            dt_situacao_atual=date(2023, 1, 3),
        )
        db.add_all([discarded_high, discarded_mid, discarded_none])
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

    assert payload["total"] == 3
    assert payload["items"]
    numeros = [item["numero_plano"] for item in payload["items"]]
    assert numeros == ["0003", "0002", "0004"]
    assert payload["items"][0]["saldo"] == 250.0
    assert payload["items"][1]["saldo"] == 67.89
    assert payload["items"][2]["saldo"] is None

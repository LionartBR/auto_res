import asyncio
import time
import pytest
from fastapi.testclient import TestClient
from datetime import date

from sirep.app.api import app
from sirep.app.tratamento import TratamentoService
from sirep.domain.enums import PlanStatus
from sirep.domain.models import DiscardedPlan, Plan, TreatmentPlan
from sirep.infra.db import SessionLocal, init_db


def reset_db() -> None:
    init_db()
    with SessionLocal() as db:
        db.query(DiscardedPlan).delete()
        db.query(TreatmentPlan).delete()
        db.query(Plan).delete()
        db.commit()


@pytest.fixture
def client():
    reset_db()
    with TestClient(app) as test_client:
        yield test_client


def test_migrar_tratamentos(client: TestClient):
    with SessionLocal() as db:
        hoje = date.today()
        plano = Plan(
            numero_plano="123456",
            situacao_atual="P.RESC.",
            saldo=5000.0,
            status=PlanStatus.PASSIVEL_RESC,
            razao_social="EMPRESA ALFA LTDA",
            tipo="ADM",
            dt_situacao_atual=hoje,
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
    assert first["tipo"] == "ADM"
    assert first["situacao_atual"] == "P.RESC."
    assert first["dt_situacao_atual"] == hoje.isoformat()


def test_migrar_inclui_planos_com_diferentes_situacoes(client: TestClient):
    hoje = date.today()
    with SessionLocal() as db:
        planos = [
            Plan(
                numero_plano="PEND001",
                situacao_atual="P.RESC.",
                saldo=1000.0,
                status=PlanStatus.PASSIVEL_RESC,
                razao_social="EMPRESA PENDENTE",
            ),
            Plan(
                numero_plano="RESC001",
                situacao_atual="RESCINDIDO",
                saldo=2000.0,
                status=PlanStatus.RESCINDIDO,
                razao_social="EMPRESA RESCINDIDA",
                data_rescisao=hoje,
            ),
            Plan(
                numero_plano="LIQ001",
                situacao_atual="LIQUIDADO",
                saldo=3000.0,
                status=PlanStatus.LIQUIDADO,
                razao_social="EMPRESA LIQUIDADA",
            ),
            Plan(
                numero_plano="GRDE001",
                situacao_atual="GRDE Emitida",
                saldo=4000.0,
                status=PlanStatus.NAO_RESCINDIDO,
                razao_social="EMPRESA GRDE",
            ),
            Plan(
                numero_plano="ESP001",
                situacao_atual="Sit especial",
                saldo=5000.0,
                status=PlanStatus.ESPECIAL,
                razao_social="EMPRESA ESPECIAL",
            ),
        ]
        db.add_all(planos)
        db.commit()

    response = client.post("/tratamentos/migrar")
    assert response.status_code == 200
    payload = response.json()
    assert payload["criados"] == len(planos)

    with SessionLocal() as db:
        tratamentos = (
            db.query(TreatmentPlan)
            .order_by(TreatmentPlan.numero_plano.asc())
            .all()
        )

    assert len(tratamentos) == len(planos)
    status_map = {trat.numero_plano: trat for trat in tratamentos}

    assert status_map["PEND001"].status == "pendente"
    assert status_map["RESC001"].status == "rescindido"
    assert status_map["RESC001"].rescisao_data == hoje
    assert status_map["LIQ001"].status == PlanStatus.LIQUIDADO.value
    assert status_map["GRDE001"].status == PlanStatus.NAO_RESCINDIDO.value
    assert status_map["ESP001"].status == PlanStatus.ESPECIAL.value


def test_migrar_materializa_planos_de_ocorrencias(client: TestClient):
    hoje = date.today()
    with SessionLocal() as db:
        ocorrencia = DiscardedPlan(
            numero_plano="OCOR001",
            situacao="RESCINDIDO",
            cnpj="12.345.678/0001-90",
            tipo="ADM",
            saldo=1234.56,
            dt_situacao_atual=hoje,
        )
        db.add(ocorrencia)
        db.commit()

    response = client.post("/tratamentos/migrar")
    assert response.status_code == 200
    payload = response.json()
    assert payload["criados"] == 1

    with SessionLocal() as db:
        plan = db.query(Plan).filter_by(numero_plano="OCOR001").one()
        tratamento = (
            db.query(TreatmentPlan)
            .filter_by(numero_plano="OCOR001")
            .one()
        )

    assert plan.status == PlanStatus.RESCINDIDO
    assert plan.data_rescisao == hoje
    assert plan.numero_inscricao == "12345678000190"
    assert tratamento.status == "rescindido"
    assert tratamento.rescisao_data == hoje

    status_body = client.get("/tratamentos/status").json()
    numeros = {plano["numero_plano"] for plano in status_body["planos"]}
    assert "OCOR001" in numeros


def test_tratamento_notepad_endpoint(client: TestClient):
    with SessionLocal() as db:
        plano = Plan(
            numero_plano="654321",
            situacao_atual="P.RESC.",
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

    response = client.get(
        "/tratamentos/rescindidos-txt",
        params={"from": hoje.isoformat(), "to": hoje.isoformat()},
    )
    assert response.status_code == 200
    body = response.text
    assert "12345678000190" in body
    assert "98765432000109" in body
    assert response.headers.get("content-disposition", "").startswith("attachment")


def test_rescindidos_txt_intervalo_invalido(client: TestClient):
    response = client.get(
        "/tratamentos/rescindidos-txt",
        params={"from": "2024-01-10", "to": "2024-01-09"},
    )
    assert response.status_code == 400


def test_tratamento_continuar_apos_restaurar(monkeypatch):
    reset_db()

    async def instant_sleep(self, duration: float) -> None:  # pragma: no cover - patched behaviour
        await asyncio.sleep(0.01)

    monkeypatch.setattr(TratamentoService, "_sleep_with_pause", instant_sleep, raising=False)

    with SessionLocal() as db:
        plano = Plan(
            numero_plano="REST001",
            situacao_atual="P.RESC.",
            saldo=1500.0,
            status=PlanStatus.PASSIVEL_RESC,
            razao_social="EMPRESA RESTAURA LTDA",
            tipo="ADM",
        )
        db.add(plano)
        db.commit()

    service = TratamentoService()
    created = service.migrar_planos()
    assert created
    assert service._queue is not None
    service.iniciar()
    time.sleep(0.1)
    service.pausar()
    time.sleep(0.1)

    novo_service = TratamentoService()
    status = novo_service.status()
    assert status["estado"] == "pausado"
    assert status["planos"]
    assert novo_service._queue is not None

    novo_service.continuar()
    deadline = time.time() + 2
    while time.time() < deadline and novo_service.estado() != "ocioso":
        time.sleep(0.05)

    assert novo_service.estado() == "ocioso"
    with SessionLocal() as db:
        tratamento = db.get(TreatmentPlan, created[0])
        assert tratamento is not None
        assert tratamento.status in {"rescindido", "descartado"}


def test_migrar_nao_inicia_sem_iniciar(monkeypatch):
    reset_db()

    async def instant_sleep(self, duration: float) -> None:  # pragma: no cover - patched behaviour
        await asyncio.sleep(0.01)

    monkeypatch.setattr(TratamentoService, "_sleep_with_pause", instant_sleep, raising=False)

    with SessionLocal() as db:
        plano1 = Plan(
            numero_plano="AUTO001",
            situacao_atual="P.RESC.",
            saldo=2000.0,
            status=PlanStatus.PASSIVEL_RESC,
            razao_social="EMPRESA AUTO 1",
            tipo="ADM",
        )
        db.add(plano1)
        db.commit()

    service = TratamentoService()
    first_ids = service.migrar_planos()
    assert first_ids
    assert service._queue is not None
    service.iniciar()

    deadline = time.time() + 2
    while time.time() < deadline and service.estado() != "ocioso":
        time.sleep(0.05)

    assert service.estado() == "ocioso"

    with SessionLocal() as db:
        plano2 = Plan(
            numero_plano="AUTO002",
            situacao_atual="P.RESC.",
            saldo=3200.0,
            status=PlanStatus.PASSIVEL_RESC,
            razao_social="EMPRESA AUTO 2",
            tipo="ADM",
        )
        db.add(plano2)
        db.commit()

    second_ids = service.migrar_planos()
    assert second_ids

    time.sleep(0.2)
    assert service.estado() in {"ocioso", "aguardando", "pausado"}

    with SessionLocal() as db:
        novos = (
            db.query(TreatmentPlan)
            .filter(TreatmentPlan.id.in_(second_ids))
            .all()
        )
        assert novos
        assert all(trat.status == "pendente" for trat in novos)


def test_migrar_ignora_planos_nao_passiveis():
    reset_db()

    with SessionLocal() as db:
        plano = Plan(
            numero_plano="IGN001",
            situacao_atual="LIQUIDADO",
            saldo=1234.56,
            status=PlanStatus.LIQUIDADO,
            razao_social="EMPRESA IGNORADA",
        )
        db.add(plano)
        db.commit()
        plano_id = plano.id

    service = TratamentoService()
    created_ids = service.migrar_planos()
    assert created_ids

    status = service.status()
    assert status["fila"] == []

    with SessionLocal() as db:
        tratamento = (
            db.query(TreatmentPlan)
            .filter(TreatmentPlan.plan_id == plano_id)
            .one()
        )
        assert tratamento.status == PlanStatus.LIQUIDADO


def test_migrar_considera_situacao_passivel_para_fila():
    reset_db()

    with SessionLocal() as db:
        plano = Plan(
            numero_plano="PAS001",
            situacao_atual="P. RESCISAO",
            saldo=9876.54,
            status=PlanStatus.NOVO,
            razao_social="EMPRESA PASSIVEL",
        )
        db.add(plano)
        db.commit()

    service = TratamentoService()
    created_ids = service.migrar_planos()
    assert created_ids

    status = service.status()
    assert set(status["fila"]) == set(created_ids)

    with SessionLocal() as db:
        tratamento = db.get(TreatmentPlan, created_ids[0])
        assert tratamento is not None
        assert tratamento.status == "pendente"

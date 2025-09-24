import pytest

from sirep.domain.enums import PlanStatus
from sirep.domain.models import Event, Plan
from sirep.infra.db import SessionLocal, init_db
from sirep.services.gestao_base import GestaoBaseData, GestaoBaseService, PlanRowEnriched


class _Collector:
    def __init__(self, data: GestaoBaseData) -> None:
        self._data = data

    def collect(self) -> GestaoBaseData:
        return self._data


def _reset_db() -> None:
    init_db()
    with SessionLocal() as db:
        db.query(Event).delete()
        db.query(Plan).delete()
        db.commit()


def _run_service(monkeypatch, data: GestaoBaseData):
    service = GestaoBaseService()
    monkeypatch.setattr(service, "_collector", lambda senha: _Collector(data))
    return service.execute()


def test_gestao_base_maps_status_and_inscricao(monkeypatch):
    _reset_db()
    data = GestaoBaseData(
        rows=[
            PlanRowEnriched(
                numero="PLN_SPECIAL",
                dt_propost="10/09/2024",
                tipo="PR1",
                situac="SIT. ESPECIAL (Portal PO)",
                resoluc="123/45",
                razao_social="Empresa Especial",
                saldo_total="10.500,00",
                cnpj="12.345.678/0001-90",
            )
        ],
        raw_lines=[],
        portal_po=[],
        descartados_974=0,
    )

    resultado = _run_service(monkeypatch, data)

    assert resultado["importados"] == 1
    assert resultado["novos"] == 1
    assert resultado["atualizados"] == 0

    with SessionLocal() as db:
        plan = db.query(Plan).filter_by(numero_plano="PLN_SPECIAL").one()
        assert plan.status == PlanStatus.ESPECIAL
        assert plan.numero_inscricao == "12345678000190"
        assert plan.representacao == "12.345.678/0001-90"
        assert plan.razao_social == "Empresa Especial"
        assert plan.resolucao == "123/45"


def test_gestao_base_preserves_existing_plan_fields(monkeypatch):
    _reset_db()
    with SessionLocal() as db:
        plano = Plan(
            numero_plano="PLN_EXIST",
            gifug="RJ",
            situacao_atual="RESCINDIDO",
            situacao_anterior="P.RESC.",
            status=PlanStatus.RESCINDIDO,
            representacao="11.111.111/0001-11",
            numero_inscricao="11111111000111",
        )
        db.add(plano)
        db.commit()

    data = GestaoBaseData(
        rows=[
            PlanRowEnriched(
                numero="PLN_EXIST",
                dt_propost="05/08/2024",
                tipo="PR2",
                situac="P.RESC.",
                resoluc="",
                razao_social="Nova Empresa",
                saldo_total="1.234,56",
                cnpj="",
            )
        ],
        raw_lines=[],
        portal_po=[],
        descartados_974=0,
    )

    resultado = _run_service(monkeypatch, data)

    assert resultado["importados"] == 1
    assert resultado["novos"] == 0
    assert resultado["atualizados"] == 1

    with SessionLocal() as db:
        plan = db.query(Plan).filter_by(numero_plano="PLN_EXIST").one()
        assert plan.gifug == "RJ"
        assert plan.numero_inscricao == "11111111000111"
        assert plan.representacao == "11.111.111/0001-11"
        assert plan.status == PlanStatus.PASSIVEL_RESC
        assert plan.situacao_anterior == "RESCINDIDO"
        assert plan.situacao_atual == "P.RESC."
        assert plan.saldo == pytest.approx(1234.56)
        assert plan.razao_social == "Nova Empresa"
        assert plan.dt_proposta.isoformat() == "2024-08-05"

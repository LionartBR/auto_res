import pytest
from typing import Optional

from sirep.domain.enums import PlanStatus
from sirep.domain.models import Event, Plan
from sirep.infra.config import settings
from sirep.infra.db import SessionLocal, init_db

from sirep.services.gestao_base import (
    GestaoBaseData,
    GestaoBaseService,
    PlanRowEnriched,
)


class _Collector:
    def __init__(self, data: GestaoBaseData) -> None:
        self._data = data

    def collect(self, progress=None) -> GestaoBaseData:  # type: ignore[override]
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


def test_collector_persists_provided_password(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)

    stored: dict[str, str] = {}

    def _fake_store(password: str | None) -> None:
        if password is not None:
            stored["value"] = password

    monkeypatch.setattr("sirep.services.gestao_base.set_gestao_base_password", _fake_store)
    monkeypatch.setattr("sirep.services.gestao_base.get_gestao_base_password", lambda: None)

    captured: dict[str, object] = {}

    class DummyCollector:
        def __init__(self, senha: str, portal_provider) -> None:  # pragma: no cover - simples
            captured["senha"] = senha
            captured["portal_provider"] = portal_provider

    monkeypatch.setattr("sirep.services.gestao_base.TerminalCollector", DummyCollector)

    service = GestaoBaseService(portal_provider=lambda: [])
    collector = service._collector("  Segredo!  ")

    assert isinstance(collector, DummyCollector)
    assert stored["value"] == "Segredo!"
    assert captured["senha"] == "Segredo!"
    assert captured["portal_provider"] is service.portal_provider


def test_collector_uses_stored_password_when_missing(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)

    stored_calls: list[str] = []

    def _fake_store(password: str | None) -> None:
        if password is not None:
            stored_calls.append(password)

    monkeypatch.setattr("sirep.services.gestao_base.set_gestao_base_password", _fake_store)
    monkeypatch.setattr(
        "sirep.services.gestao_base.get_gestao_base_password", lambda: "Persistida!"
    )

    class DummyCollector:
        def __init__(self, senha: str, portal_provider) -> None:  # pragma: no cover - simples
            self.senha = senha
            self.portal_provider = portal_provider

    monkeypatch.setattr("sirep.services.gestao_base.TerminalCollector", DummyCollector)

    service = GestaoBaseService()
    collector = service._collector(None)

    assert isinstance(collector, DummyCollector)
    assert collector.senha == "Persistida!"
    assert stored_calls == []


def test_execute_emits_progress_events(monkeypatch):
    _reset_db()
    data = GestaoBaseData(
        rows=[
            PlanRowEnriched(
                numero="PLN_PROGRESS",
                dt_propost="01/01/2024",
                tipo="PR1",
                situac="P.RESC.",
                resoluc="123/45",
                razao_social="Empresa Progresso",
                saldo_total="1.000,00",
                cnpj="12.345.678/0001-90",
            )
        ],
        raw_lines=[],
        portal_po=[],
        descartados_974=0,
    )

    eventos: list[tuple[float, Optional[int], Optional[str]]] = []

    class TrackingCollector:
        def __init__(self, payload: GestaoBaseData) -> None:
            self.payload = payload

        def collect(self, progress=None) -> GestaoBaseData:  # type: ignore[override]
            if progress:
                progress(20.0, 1, "Dados coletados na E555")
            return self.payload

    service = GestaoBaseService()
    monkeypatch.setattr(service, "_collector", lambda senha: TrackingCollector(data))

    service.execute(progress_callback=lambda p, etapa, msg: eventos.append((p, etapa, msg)))

    assert eventos, "deve registrar ao menos um evento de progresso"
    assert any(etapa == 4 and round(percent, 1) == 100.0 for percent, etapa, _ in eventos)

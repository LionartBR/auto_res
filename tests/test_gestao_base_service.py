import pytest
from datetime import datetime, timezone
from typing import Optional

from sirep.domain.enums import PlanStatus
from sirep.domain.models import DiscardedPlan, Event, Plan
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
        db.query(DiscardedPlan).delete()
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


def test_gestao_base_real_capture_registra_ocorrencias(monkeypatch):
    _reset_db()
    monkeypatch.setattr(settings, "DRY_RUN", False)

    data = GestaoBaseData(
        rows=[
            PlanRowEnriched(
                numero="PLN_SPECIAL",
                dt_propost="01/02/2024",
                tipo="PR1",
                situac="SIT. ESPECIAL (Portal PO)",
                resoluc="",
                razao_social="Empresa Especial",
                saldo_total="10.000,00",
                cnpj="11.222.333/0001-44",
            ),
            PlanRowEnriched(
                numero="PLN_PASSIVO",
                dt_propost="05/02/2024",
                tipo="PR2",
                situac="P.RESC.",
                resoluc="",
                razao_social="Empresa Passiva",
                saldo_total="2.500,00",
                cnpj="55.666.777/0001-88",
            ),
            PlanRowEnriched(
                numero="PLN_GRDE",
                dt_propost="10/02/2024",
                tipo="PR3",
                situac="GRDE Emitida",
                resoluc="",
                razao_social="Empresa GRDE",
                saldo_total="",
                cnpj="22.333.444/0001-55",
            ),
            PlanRowEnriched(
                numero="PLN_LIQ",
                dt_propost="12/02/2024",
                tipo="PR4",
                situac="Liquidado",
                resoluc="",
                razao_social="Empresa Liquidada",
                saldo_total="5.500,00",
                cnpj="77.888.999/0001-00",
            ),
        ],
        raw_lines=[],
        portal_po=[],
        descartados_974=0,
    )

    resultado = _run_service(monkeypatch, data)

    assert resultado["importados"] == 4

    with SessionLocal() as db:
        ocorrencias = db.query(DiscardedPlan).all()

    assert len(ocorrencias) == 3
    encontrados = {occ.numero_plano: occ for occ in ocorrencias}
    assert set(encontrados) == {"PLN_SPECIAL", "PLN_GRDE", "PLN_LIQ"}
    assert encontrados["PLN_SPECIAL"].situacao.upper().startswith("SIT")
    assert encontrados["PLN_LIQ"].situacao.upper().startswith("LIQ")
    assert encontrados["PLN_GRDE"].situacao.upper().startswith("GRDE")
    assert encontrados["PLN_GRDE"].saldo is None
    assert encontrados["PLN_SPECIAL"].cnpj == "11.222.333/0001-44"


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


def test_gestao_base_persiste_parcelas_e_dias_em_atraso(monkeypatch):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2024, 9, 15, 12, 0, tzinfo=timezone.utc)
            if tz is None:
                return base
            return base.astimezone(tz)

        @classmethod
        def utcnow(cls):
            return cls.now(timezone.utc)

    monkeypatch.setattr("sirep.services.gestao_base.datetime", _FixedDatetime)

    _reset_db()

    data = GestaoBaseData(
        rows=[
            PlanRowEnriched(
                numero="PLN_ATRASO",
                dt_propost="01/03/2024",
                tipo="PR1",
                situac="P.RESC.",
                resoluc="",
                razao_social="Empresa Inadimplente",
                saldo_total="2.000,00",
                cnpj="00.111.222/0001-33",
                parcelas_atraso=[
                    {"parcela": "104", "valor": "700,00", "vencimento": "01/05/2024"},
                    {"parcela": "103", "valor": "700,00", "vencimento": "01/06/2024"},
                    {"parcela": "102", "valor": "700,00", "vencimento": "01/07/2024"},
                    {"parcela": "101", "valor": "700,00", "vencimento": "01/08/2024"},
                ],
            )
        ],
        raw_lines=[],
        portal_po=[],
        descartados_974=0,
    )

    resultado = _run_service(monkeypatch, data)
    assert resultado["importados"] == 1

    with SessionLocal() as db:
        plan = db.query(Plan).filter_by(numero_plano="PLN_ATRASO").one()

    assert plan.dias_em_atraso == 137
    assert plan.parcelas_atraso is not None
    assert len(plan.parcelas_atraso) == 3
    parcelas = plan.parcelas_atraso
    assert parcelas[0]["parcela"] == "104"
    assert parcelas[0]["vencimento"] == "2024-05-01"
    assert parcelas[1]["parcela"] == "103"
    assert parcelas[1]["vencimento"] == "2024-06-01"
    assert parcelas[2]["parcela"] == "102"
    assert parcelas[2]["vencimento"] == "2024-07-01"
    assert "dias_em_atraso" not in parcelas[0]


def test_gestao_base_limpa_parcelas_em_atraso_quando_regulariza(monkeypatch):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: Optional[timezone] = None):  # type: ignore[override]
            base = datetime(2024, 9, 15, 12, 0, tzinfo=timezone.utc)
            if tz is None:
                return base
            return base.astimezone(tz)

        @classmethod
        def utcnow(cls):  # pragma: no cover - compat
            return cls.now(timezone.utc)

    monkeypatch.setattr("sirep.services.gestao_base.datetime", _FixedDatetime)

    _reset_db()

    dados_iniciais = GestaoBaseData(
        rows=[
            PlanRowEnriched(
                numero="PLN_REGULARIZA",
                dt_propost="01/03/2024",
                tipo="PR1",
                situac="P.RESC.",
                resoluc="",
                razao_social="Empresa Inadimplente",
                saldo_total="2.000,00",
                cnpj="00.111.222/0001-33",
                parcelas_atraso=[
                    {"parcela": "104", "valor": "700,00", "vencimento": "01/05/2024"},
                    {"parcela": "103", "valor": "700,00", "vencimento": "01/06/2024"},
                    {"parcela": "102", "valor": "700,00", "vencimento": "01/07/2024"},
                ],
            )
        ],
        raw_lines=[],
        portal_po=[],
        descartados_974=0,
    )

    _run_service(monkeypatch, dados_iniciais)

    dados_regularizado = GestaoBaseData(
        rows=[
            PlanRowEnriched(
                numero="PLN_REGULARIZA",
                dt_propost="01/03/2024",
                tipo="PR1",
                situac="REGULAR",
                resoluc="",
                razao_social="Empresa Inadimplente",
                saldo_total="2.000,00",
                cnpj="00.111.222/0001-33",
                parcelas_atraso=[],
                dias_atraso=None,
            )
        ],
        raw_lines=[],
        portal_po=[],
        descartados_974=0,
    )

    _run_service(monkeypatch, dados_regularizado)

    with SessionLocal() as db:
        plan = db.query(Plan).filter_by(numero_plano="PLN_REGULARIZA").one()

    assert plan.parcelas_atraso is None
    assert plan.dias_em_atraso is None


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

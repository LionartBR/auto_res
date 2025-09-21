from sirep.app.captura import CapturaService
from sirep.app.captura import CapturaService
from sirep.domain.models import PlanLog
from sirep.infra.db import SessionLocal, init_db


def _limpar_historico():
    with SessionLocal() as db:
        db.query(PlanLog).delete()
        db.commit()


def test_historico_persiste_entre_instancias():
    init_db()
    _limpar_historico()

    service = CapturaService()
    service._history_limit = 5

    for idx in range(7):
        service._registrar_historico(
            numero_plano=f"PLN-{idx}",
            progresso=idx % 5,
            etapa=f"Etapa {idx % 4}",
            mensagem=f"Evento {idx}",
        )

    with SessionLocal() as db:
        assert db.query(PlanLog).count() == 7

    # Garante que o próprio serviço respeita o limite em memória
    historico_atual = service.status().historico
    assert len(historico_atual) == 5
    assert [item.mensagem for item in historico_atual] == [f"Evento {i}" for i in range(2, 7)]

    # Simula reinício da aplicação criando uma nova instância
    novo_service = CapturaService()
    novo_service._history_limit = 5

    status = novo_service.status()
    assert len(status.historico) == 5
    assert [item.mensagem for item in status.historico] == [f"Evento {i}" for i in range(2, 7)]
    assert status.ultima_atualizacao == status.historico[-1].timestamp


def test_historico_carregado_mantem_fuso_horario():
    init_db()
    _limpar_historico()

    service = CapturaService()
    service._registrar_historico(
        numero_plano="PLN-001",
        progresso=1,
        etapa="Etapa 1",
        mensagem="Evento com fuso",
    )

    novo_service = CapturaService()
    status = novo_service.status()

    assert status.historico, "Histórico deveria conter ao menos um evento"
    timestamp = status.historico[-1].timestamp
    assert timestamp.endswith("+00:00")
    assert status.ultima_atualizacao.endswith("+00:00")

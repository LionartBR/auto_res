import asyncio
import time

from sirep.app.captura import CapturaService
from sirep.infra.db import init_db


def _esperar_estado(servico: CapturaService, estado: str, timeout: float = 5.0) -> None:
    limite = time.time() + timeout
    while time.time() < limite:
        if servico.status().estado == estado:
            return
        time.sleep(0.05)
    raise AssertionError(f"estado atual '{servico.status().estado}' diferente de '{estado}'")


def test_pausar_pos_conclusao_permite_reiniciar(monkeypatch):
    init_db()

    service = CapturaService()
    service._total_alvos = 1
    service._velocidade = 1
    service._step_min = 0
    service._step_max = 0

    async def _sleep_rapido(self, duration: float) -> None:  # pragma: no cover - trivial
        await asyncio.sleep(0)

    monkeypatch.setattr(CapturaService, "_sleep_with_pause", _sleep_rapido, raising=False)

    service.iniciar()
    _esperar_estado(service, "concluido")
    assert service.status().estado == "concluido"

    service.pausar()
    assert service.status().estado == "concluido"

    service.iniciar()
    _esperar_estado(service, "concluido")
    assert service.status().estado == "concluido"

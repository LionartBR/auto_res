import asyncio
import time
from datetime import datetime, timezone

import pytest

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
    assert service._loop is not None
    assert service._loop_thread is not None
    _esperar_estado(service, "concluido")
    assert service.status().estado == "concluido"

    service.pausar()
    assert service.status().estado == "concluido"

    service.iniciar()
    _esperar_estado(service, "concluido")
    assert service.status().estado == "concluido"


@pytest.mark.parametrize("anyio_backend", ["asyncio"])
@pytest.mark.anyio
async def test_persistir_historico_async_fallback_runtimeerror(monkeypatch):
    init_db()

    service = CapturaService()
    fallback_args: dict[str, tuple] = {}

    async def raise_runtime_error(*args, **kwargs):
        raise RuntimeError("Executor shutdown has been called")

    monkeypatch.setattr(asyncio, "to_thread", raise_runtime_error)

    def fake_sync(numero_plano, mensagem, status, etapa_numero, etapa_nome, created_at):
        fallback_args["args"] = (
            numero_plano,
            mensagem,
            status,
            etapa_numero,
            etapa_nome,
            created_at,
        )
        return True

    monkeypatch.setattr(service, "_persistir_historico_sync", fake_sync)

    resultado = await service._persistir_historico_async(
        "0001",
        "Registro teste",
        "INFO",
        1,
        "Etapa teste",
        datetime.now(timezone.utc),
    )

    assert resultado is True
    assert "args" in fallback_args

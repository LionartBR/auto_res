from __future__ import annotations

import asyncio
import logging
import random
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Dict, List, Literal, Optional

from sirep.infra.db import SessionLocal
from sirep.infra.repositories import (
    PlanRepository,
    EventRepository,
    OccurrenceRepository,
    CaptureEventRepository,
)
from sirep.domain.enums import PlanStatus, Step

logger = logging.getLogger(__name__)

Estado = Literal["ocioso", "executando", "pausado", "concluido"]
TIPOS = ("ADM", "INS", "JUD", "AI", "AJ")
SITS_ALT = ("SIT ESPECIAL", "LIQUIDADO", "RESCINDIDO", "GRDE Emitida")

@dataclass
class PlanoProgresso:
    numero_plano: str
    progresso: int = 0
    etapas: List[str] = field(default_factory=lambda: ["Captura", "Situação especial", "Liquidação anterior", "GRDE"])


@dataclass
class PlanoHistorico:
    numero_plano: str
    mensagem: str
    progresso: int
    etapa: str
    timestamp: str

@dataclass
class CapturaStatus:
    estado: Estado = "ocioso"
    processados: int = 0
    novos: int = 0
    falhas: int = 0
    em_progresso: Dict[str, PlanoProgresso] = field(default_factory=dict)
    ultima_atualizacao: Optional[str] = None
    last_error: Optional[str] = None  # <<< surfaced
    historico: List[PlanoHistorico] = field(default_factory=list)

class CapturaService:
    def __init__(self) -> None:
        self._status = CapturaStatus()
        self._loop_task: Optional[asyncio.Future] = None
        self._pause_evt: Optional[asyncio.Event] = None
        self._stop_evt: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()
        self._total_alvos = 50
        self._velocidade = 1
        self._step_min = 0.40
        self._step_max = 0.80
        self._history_limit = 200
        self._history_loaded = False

    def status(self) -> CapturaStatus:
        self._ensure_history_loaded()
        return self._status

    def reset_estado(self) -> None:
        self._status = CapturaStatus()
        self._loop_task = None
        self._pause_evt = None
        self._stop_evt = None
        self._history_loaded = False

    @staticmethod
    async def _call_sync(func) -> None:
        func()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            self._loop = loop
            return loop

        existing = self._loop
        if existing and existing.is_running():
            return existing

        loop = asyncio.new_event_loop()
        self._loop = loop
        self._loop_ready.clear()

        def runner() -> None:
            asyncio.set_event_loop(loop)
            self._loop_ready.set()
            loop.run_forever()

        self._loop_thread = threading.Thread(target=runner, name="captura-loop", daemon=True)
        self._loop_thread.start()
        self._loop_ready.wait()
        return loop

    def _run_on_loop(self, func, *, wait: bool = False, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        target = loop or self._loop
        if target is None:
            return

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is target:
            func()
            return

        fut = asyncio.run_coroutine_threadsafe(self._call_sync(func), target)
        if wait:
            fut.result()

    async def _wait_resume(self) -> None:
        while True:
            evt = self._pause_evt
            if evt is None or evt.is_set():
                return
            await evt.wait()

    async def _sleep_with_pause(self, duration: float) -> None:
        remaining = duration
        while remaining > 0:
            await self._wait_resume()
            interval = min(0.1, remaining)
            await asyncio.sleep(interval)
            evt = self._pause_evt
            if evt is not None and not evt.is_set():
                continue
            remaining -= interval

    def iniciar(self) -> None:
        self._ensure_history_loaded()
        if self._status.estado in ("executando", "pausado"):
            logger.info("captura já em %s", self._status.estado)
            return

        historico_anterior = list(self._status.historico)
        ultima_atualizacao = self._status.ultima_atualizacao
        self._status = CapturaStatus(
            estado="executando",
            historico=historico_anterior,
            ultima_atualizacao=ultima_atualizacao,
        )

        self._registrar_historico(
            numero_plano="",
            progresso=0,
            etapa="",
            mensagem="Processamento iniciado.",
        )

        loop = self._ensure_loop()
        def prepare_events() -> None:
            self._pause_evt = asyncio.Event()
            self._pause_evt.set()
            self._stop_evt = asyncio.Event()

        self._run_on_loop(prepare_events, wait=True, loop=loop)

        if self._pause_evt is None or self._stop_evt is None:
            raise RuntimeError("falha ao inicializar eventos da captura")

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is loop:
            self._loop_task = loop.create_task(self._run(), name="captura-run")
        else:
            self._loop_task = asyncio.run_coroutine_threadsafe(self._run(), loop)
        logger.info("captura iniciada")

    def pausar(self) -> None:
        if self._status.estado != "executando":
            return
        loop_task = self._loop_task
        is_running = False
        if loop_task is not None:
            try:
                is_running = not loop_task.done()
            except Exception:
                logger.exception("falha ao verificar estado da captura")
        if not is_running:
            # Nothing to pause; keep a terminal state so a new execution can start.
            self._status.estado = "concluido"
            logger.info("captura já finalizada; ignorando pedido de pausa")
            return

        self._status.estado = "pausado"
        if self._pause_evt is not None:
            self._run_on_loop(self._pause_evt.clear)
        self._registrar_historico(
            numero_plano="",
            progresso=0,
            etapa="",
            mensagem="Processamento pausado.",
        )
        logger.info("captura pausada")

    def continuar(self) -> None:
        if self._status.estado != "pausado":
            return
        if self._pause_evt is None:
            # The processing loop is no longer active; restore a safe terminal state.
            self._status.estado = "concluido"
            logger.info("nenhuma captura ativa para continuar; estado definido como concluído")
            return
        self._status.estado = "executando"
        if self._pause_evt is not None:
            self._run_on_loop(self._pause_evt.set)
        self._registrar_historico(
            numero_plano="",
            progresso=0,
            etapa="",
            mensagem="Processamento retomado.",
        )
        logger.info("captura continuada")

    async def _run(self) -> None:
        pause_evt = self._pause_evt
        stop_evt = self._stop_evt
        if pause_evt is None or stop_evt is None:
            logger.error("eventos de controle não inicializados antes da captura")
            self._status.estado = "concluido"
            return

        try:
            alvo, gerados = self._total_alvos, 0
            while not stop_evt.is_set() and gerados < alvo:
                await self._wait_resume()
                for _ in range(min(self._velocidade, alvo - gerados)):
                    await self._wait_resume()
                    if stop_evt.is_set():
                        break
                    numero = self._gerar_numero()
                    try:
                        asyncio.get_running_loop().create_task(
                            self._processar_plano(numero), name=f"plano-{numero}"
                        )
                    except Exception:
                        self._status.last_error = traceback.format_exc()
                        logger.exception("erro ao criar task do plano %s", numero)
                    gerados += 1
                await self._sleep_with_pause(1.0)

            while self._status.estado != "pausado" and any(p.progresso < 4 for p in self._status.em_progresso.values()):
                await asyncio.sleep(0.2)

        except Exception:
            self._status.last_error = traceback.format_exc()
            logger.exception("erro no loop principal da captura")
        finally:
            pending_work = any(
                progresso.progresso < 4 for progresso in self._status.em_progresso.values()
            )
            should_mark_concluded = self._status.estado != "pausado" or not pending_work
            if should_mark_concluded:
                already_concluded = self._status.estado == "concluido"
                self._status.estado = "concluido"
                last_message = self._status.historico[-1].mensagem if self._status.historico else None
                if not (already_concluded and last_message == "Processamento concluído."):
                    self._registrar_historico(
                        numero_plano="",
                        progresso=4,
                        etapa="",
                        mensagem="Processamento concluído.",
                    )
            if self._pause_evt is not None:
                self._pause_evt.set()
            self._loop_task = None
            self._pause_evt = None
            self._stop_evt = None
            logger.info("captura finalizada: %s", self._status.estado)

    def _obter_etapa(self, numero_plano: str, progresso: int) -> str:
        info = self._status.em_progresso.get(numero_plano)
        if info and info.etapas:
            idx = min(max(progresso - 1, 0), len(info.etapas) - 1)
            return info.etapas[idx]
        return ""

    def _registrar_historico(
        self,
        *,
        numero_plano: str,
        progresso: int,
        etapa: str,
        mensagem: str,
    ) -> None:
        self._ensure_history_loaded()
        timestamp_dt = datetime.now(timezone.utc)
        timestamp = timestamp_dt.isoformat()
        evento = PlanoHistorico(
            numero_plano=numero_plano,
            mensagem=mensagem,
            progresso=progresso,
            etapa=etapa,
            timestamp=timestamp,
        )
        try:
            with SessionLocal() as db:
                repo = CaptureEventRepository(db)
                repo.add_event(
                    numero_plano=numero_plano,
                    mensagem=mensagem,
                    progresso=progresso,
                    etapa=etapa,
                    timestamp=timestamp_dt,
                )
                db.commit()
        except Exception:
            logger.exception("erro ao persistir histórico da captura")
        historico = self._status.historico
        historico.append(evento)
        if len(historico) > self._history_limit:
            del historico[: len(historico) - self._history_limit]
        self._status.ultima_atualizacao = timestamp

    def _ensure_history_loaded(self) -> None:
        if self._history_loaded:
            return
        try:
            with SessionLocal() as db:
                repo = CaptureEventRepository(db)
                eventos = repo.get_recent(self._history_limit)
        except Exception:
            logger.exception("erro ao carregar histórico da captura")
            return

        historico: List[PlanoHistorico] = []
        for ev in reversed(eventos):
            timestamp_dt = ev.timestamp
            if timestamp_dt and timestamp_dt.tzinfo is None:
                timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
            ts = timestamp_dt.isoformat() if timestamp_dt else None
            historico.append(
                PlanoHistorico(
                    numero_plano=ev.numero_plano,
                    mensagem=ev.mensagem,
                    progresso=ev.progresso,
                    etapa=ev.etapa,
                    timestamp=ts or datetime.now(timezone.utc).isoformat(),
                )
            )
        self._status.historico = historico
        if historico:
            self._status.ultima_atualizacao = historico[-1].timestamp
        self._history_loaded = True

    async def _processar_plano(self, numero_plano: str) -> None:
        st = self._status
        try:
            await self._wait_resume()
            st.em_progresso[numero_plano] = PlanoProgresso(numero_plano, 0)
            cnpj = self._gerar_cnpj()
            saldo = round(random.uniform(1_000, 150_000), 2)
            hoje: date = datetime.now(timezone.utc).date()
            tipo = random.choice(TIPOS)

            await self._sleep_with_pause(random.uniform(self._step_min, self._step_max))
            await self._wait_resume()
            st.em_progresso[numero_plano].progresso = 1

            await self._sleep_with_pause(random.uniform(self._step_min, self._step_max))
            await self._wait_resume()
            st.em_progresso[numero_plano].progresso = 2
            if random.random() < 0.05:
                await self._wait_resume()
                with SessionLocal() as db:
                    OccurrenceRepository(db).add(
                        numero_plano=numero_plano,
                        situacao="SIT ESPECIAL",
                        cnpj=cnpj,
                        tipo=tipo,
                        saldo=saldo,
                        dt_situacao_atual=hoje,
                    )
                    db.commit()
                await self._wait_resume()
                self._registrar_historico(
                    numero_plano=numero_plano,
                    progresso=2,
                    etapa=self._obter_etapa(numero_plano, 2),
                    mensagem="Descartado: SIT ESPECIAL",
                )
                await self._wait_resume()
                st.falhas += 1
                st.processados += 1
                return

            await self._sleep_with_pause(random.uniform(self._step_min, self._step_max))
            await self._wait_resume()
            st.em_progresso[numero_plano].progresso = 3
            if random.random() < 0.04:
                sit = random.choice(("LIQUIDADO", "RESCINDIDO"))
                await self._wait_resume()
                with SessionLocal() as db:
                    OccurrenceRepository(db).add(
                        numero_plano=numero_plano,
                        situacao=sit,
                        cnpj=cnpj,
                        tipo=tipo,
                        saldo=saldo,
                        dt_situacao_atual=hoje,
                    )
                    db.commit()
                await self._wait_resume()
                self._registrar_historico(
                    numero_plano=numero_plano,
                    progresso=3,
                    etapa=self._obter_etapa(numero_plano, 3),
                    mensagem=f"Descartado: {sit}",
                )
                await self._wait_resume()
                st.falhas += 1
                st.processados += 1
                return

            await self._sleep_with_pause(random.uniform(self._step_min, self._step_max))
            await self._wait_resume()
            if random.random() < 0.04:
                await self._wait_resume()
                with SessionLocal() as db:
                    OccurrenceRepository(db).add(
                        numero_plano=numero_plano,
                        situacao="GRDE Emitida",
                        cnpj=cnpj,
                        tipo=tipo,
                        saldo=saldo,
                        dt_situacao_atual=hoje,
                    )
                    db.commit()
                await self._wait_resume()
                self._registrar_historico(
                    numero_plano=numero_plano,
                    progresso=4,
                    etapa=self._obter_etapa(numero_plano, 4),
                    mensagem="Descartado: GRDE Emitida",
                )
                await self._wait_resume()
                st.falhas += 1
                st.processados += 1
                return
            st.em_progresso[numero_plano].progresso = 4

            if random.random() < 0.03:
                situacao_final = random.choice(SITS_ALT)
                await self._wait_resume()
                with SessionLocal() as db:
                    OccurrenceRepository(db).add(
                        numero_plano=numero_plano,
                        situacao=situacao_final,
                        cnpj=cnpj,
                        tipo=tipo,
                        saldo=saldo,
                        dt_situacao_atual=hoje,
                    )
                    db.commit()
                await self._wait_resume()
                self._registrar_historico(
                    numero_plano=numero_plano,
                    progresso=4,
                    etapa=self._obter_etapa(numero_plano, 4),
                    mensagem=f"Descartado: {situacao_final}",
                )
                await self._wait_resume()
                st.falhas += 1
                st.processados += 1
                return

            await self._wait_resume()
            with SessionLocal() as db:
                plans = PlanRepository(db)
                events = EventRepository(db)
                p = plans.upsert(
                    numero_plano=numero_plano,
                    gifug="MZ",
                    situacao_atual="P. RESC",
                    situacao_anterior="P. RESC",
                    dias_em_atraso=random.randint(90, 120),
                    tipo=tipo,
                    dt_situacao_atual=hoje,
                    saldo=saldo,
                    cmb_ajuste="",
                    justificativa="",
                    matricula="",
                    dt_parcela_atraso=None,
                    representacao="",
                    status=PlanStatus.PASSIVEL_RESC,
                    tipo_parcelamento=tipo,
                    saldo_total=saldo,
                )
                events.log(p.id, Step.ETAPA_1, "Capturado via simulação")
                db.commit()

            await self._wait_resume()
            st.novos += 1
            st.processados += 1
            await self._wait_resume()
            self._registrar_historico(
                numero_plano=numero_plano,
                progresso=4,
                etapa=self._obter_etapa(numero_plano, 4),
                mensagem="Capturado com sucesso",
            )

        except Exception:
            await self._wait_resume()
            st.falhas += 1
            st.last_error = traceback.format_exc()
            logger.exception("erro ao processar plano %s", numero_plano)
            info_atual = st.em_progresso.get(numero_plano)
            progresso_atual = info_atual.progresso if info_atual else 0
            etapa = self._obter_etapa(numero_plano, progresso_atual or 1)
            await self._wait_resume()
            self._registrar_historico(
                numero_plano=numero_plano,
                progresso=progresso_atual,
                etapa=etapa,
                mensagem="Falha inesperada",
            )
        finally:
            await self._wait_resume()
            st.em_progresso.pop(numero_plano, None)
            st.ultima_atualizacao = datetime.now(timezone.utc).isoformat()

    def _gerar_numero(self) -> str:
        ano = random.randint(2003, 2025)
        sufixo = random.randint(1010, 96052)
        return f"{ano:04d}{sufixo:05d}"

    def _gerar_cnpj(self) -> str:
        nums = [random.randint(0,9) for _ in range(8)] + [0,0,0,1]
        def dv(digs, pesos):
            s = sum(d*p for d,p in zip(digs, pesos))
            r = s % 11
            return 0 if r < 2 else 11 - r
        d1 = dv(nums, [5,4,3,2,9,8,7,6,5,4,3,2])
        d2 = dv(nums + [d1], [6,5,4,3,2,9,8,7,6,5,4,3,2])
        c = nums + [d1, d2]
        return f"{c[0]}{c[1]}.{c[2]}{c[3]}{c[4]}.{c[5]}{c[6]}{c[7]}/{c[8]}{c[9]}{c[10]}{c[11]}-{c[12]}{c[13]}"

captura = CapturaService()

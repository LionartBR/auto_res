from __future__ import annotations

import asyncio
import logging
import random
import traceback
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from typing import Any, Callable, Dict, List, Literal, Optional

from sirep.app.async_loop import AsyncLoopMixin
from sirep.infra.db import SessionLocal
from sirep.infra.repositories import (
    PlanRepository,
    EventRepository,
    OccurrenceRepository,
    PlanLogRepository,
)
from sirep.domain.logs import GESTAO_STAGE_LABELS, infer_gestao_stage_numero
from sirep.shared.fakes import TIPOS_REPRESENTACAO, gerar_razao_social
from sirep.domain.enums import PlanStatus, Step
from sirep.services.gestao_base import GestaoBaseService
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

Estado = Literal["ocioso", "executando", "pausado", "concluido"]
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
    status: str = "INFO"
    etapa_nome: Optional[str] = None

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
    progress_override: Optional[float] = None
    progress_stage: Optional[str] = None

class CapturaService(AsyncLoopMixin):
    _ASYNC_LOOP_THREAD_NAME = "captura-loop"

    def __init__(self) -> None:
        super().__init__()
        self._status = CapturaStatus()
        self._loop_task: Optional[asyncio.Future] = None
        self._pause_evt: Optional[asyncio.Event] = None
        self._stop_evt: Optional[asyncio.Event] = None
        self._gestao_base_service = GestaoBaseService()
        self._default_total_alvos = 50
        self._total_alvos = self._default_total_alvos
        self._velocidade = 1
        self._step_min = 0.40
        self._step_max = 0.80
        self._history_limit = 200
        self._history_loaded = False
        self._history_retry_at: Optional[datetime] = None
        self._last_progress_message: Optional[str] = None
        self._last_progress_percent: float = 0.0

    def status(self) -> CapturaStatus:
        self._ensure_history_loaded()
        return self._status

    @property
    def total_alvos(self) -> int:
        """Quantidade total de planos simulados por execução."""

        return self._total_alvos

    def progresso_percentual(self) -> float:
        """Percentual de progresso considerando o total configurado."""

        override = self._status.progress_override
        if override is not None:
            return round(max(0.0, min(override, 100.0)), 1)

        total = self._total_alvos
        if total <= 0:
            return 0.0
        concluido = min(self._status.processados, total)
        return round((concluido / total) * 100, 1)

    def reset_estado(self) -> None:
        self._status = CapturaStatus()
        self._loop_task = None
        self._pause_evt = None
        self._stop_evt = None
        self._history_loaded = False
        self._history_retry_at = None
        self._total_alvos = self._default_total_alvos
        self._last_progress_message = None
        self._last_progress_percent = 0.0

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

    def _executar_captura_real_sync(
        self,
        *,
        progress_callback: Optional[Callable[[float, Optional[int], Optional[str]], None]] = None,
    ) -> Any:
        """Executa a captura real de Gestão da Base em thread separada."""

        return self._gestao_base_service.execute(progress_callback=progress_callback)

    def _aplicar_progresso_real(
        self, percent: float, etapa: Optional[int], mensagem: Optional[str]
    ) -> None:
        percent = max(0.0, min(percent, 100.0))
        st = self._status
        anterior = st.progress_override if st.progress_override is not None else self._last_progress_percent
        if percent < anterior:
            percent = anterior
        st.progress_override = round(percent, 1)
        self._last_progress_percent = percent
        st.ultima_atualizacao = datetime.now(timezone.utc).isoformat()
        if mensagem:
            st.progress_stage = mensagem
        if etapa and mensagem and mensagem != self._last_progress_message:
            etapa_label = GESTAO_STAGE_LABELS.get(etapa, "Gestão da Base")
            self._registrar_historico(
                numero_plano="",
                progresso=etapa,
                etapa=etapa_label,
                mensagem=mensagem,
                status="INFO",
            )
            self._last_progress_message = mensagem

    async def _run_captura_real(self) -> bool:
        """Tenta executar a captura real; retorna ``True`` em caso de sucesso."""

        def _safe_int(value: Any) -> int:
            try:
                return int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return 0

        loop = asyncio.get_running_loop()
        st = self._status
        st.progress_override = 0.0
        st.progress_stage = "Captura real em andamento"
        self._last_progress_message = None
        self._last_progress_percent = 0.0

        def _notify(percent: float, etapa: Optional[int] = None, mensagem: Optional[str] = None) -> None:
            try:
                loop.call_soon_threadsafe(self._aplicar_progresso_real, percent, etapa, mensagem)
            except RuntimeError:
                logger.debug("loop encerrado; ignorando atualização de progresso da captura real")

        try:
            resultado = await asyncio.to_thread(
                self._executar_captura_real_sync, progress_callback=_notify
            )
        except Exception:
            st.last_error = traceback.format_exc()
            logger.exception("erro ao executar captura real da Gestão da Base")
            self._status.progress_override = None
            self._status.progress_stage = None
            self._registrar_historico(
                numero_plano="",
                progresso=1,
                etapa=GESTAO_STAGE_LABELS.get(1, "Gestão da Base"),
                mensagem=(
                    "Captura real indisponível; executando fallback com dados simulados."
                ),
                status="FALHA",
            )
            return False

        if not isinstance(resultado, dict):
            logger.error("resultado inesperado da captura real: %r", resultado)
            self._status.progress_override = None
            self._status.progress_stage = None
            self._registrar_historico(
                numero_plano="",
                progresso=1,
                etapa=GESTAO_STAGE_LABELS.get(1, "Gestão da Base"),
                mensagem=(
                    "Retorno inválido da captura real; executando fallback com dados simulados."
                ),
                status="FALHA",
            )
            return False

        erro = resultado.get("error")
        if erro:
            mensagem_erro = str(erro)
            st.last_error = mensagem_erro
            logger.warning(
                "captura real bloqueada: %s; executando fallback simulado", mensagem_erro
            )
            self._status.progress_override = None
            self._status.progress_stage = None
            self._registrar_historico(
                numero_plano="",
                progresso=1,
                etapa=GESTAO_STAGE_LABELS.get(1, "Gestão da Base"),
                mensagem=(
                    "Captura real bloqueada; executando fallback com dados simulados."
                ),
                status="FALHA",
            )
            return False

        processados = _safe_int(resultado.get("importados"))
        novos = _safe_int(resultado.get("novos"))
        atualizados = _safe_int(resultado.get("atualizados"))

        detalhes: list[str] = []
        if novos:
            detalhes.append(f"{novos} novos")
        if atualizados:
            detalhes.append(f"{atualizados} atualizados")
        resumo = (
            f"{processados} planos" + (f" ({', '.join(detalhes)})" if detalhes else "")
            if processados
            else "Nenhum plano processado"
        )

        st.processados = processados
        st.novos = novos
        st.falhas = 0
        st.em_progresso.clear()
        st.last_error = None
        st.progress_override = None
        st.progress_stage = None
        self._last_progress_message = None
        self._last_progress_percent = 0.0

        self._total_alvos = max(processados, 1) if processados else self._default_total_alvos
        st.estado = "concluido"
        st.ultima_atualizacao = datetime.now(timezone.utc).isoformat()
        self._registrar_historico(
            numero_plano="",
            progresso=4,
            etapa=GESTAO_STAGE_LABELS.get(4, "Gestão da Base"),
            mensagem=f"Captura real concluída: {resumo}.",
            status="SUCESSO",
        )
        logger.info("captura real concluída com sucesso: %s", resumo)
        return True

    def iniciar(self) -> None:
        self._ensure_history_loaded()
        if self._status.estado in ("executando", "pausado"):
            logger.info("captura já em %s", self._status.estado)
            return

        historico_anterior = list(self._status.historico)
        ultima_atualizacao = self._status.ultima_atualizacao
        self._total_alvos = self._default_total_alvos
        self._status = CapturaStatus(
            estado="executando",
            historico=historico_anterior,
            ultima_atualizacao=ultima_atualizacao,
        )

        self._registrar_historico(
            numero_plano=None,
            progresso=0,
            etapa="",
            mensagem="Processamento iniciado.",
            status="INICIO",
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
        numero_atual, etapa_atual = self._plano_em_execucao()
        etapa_nome = GESTAO_STAGE_LABELS.get(etapa_atual) if etapa_atual else ""
        mensagem = (
            f"Etapa {etapa_atual} pausada" if etapa_atual else "Processamento pausado."
        )
        self._registrar_historico(
            numero_plano=numero_atual,
            progresso=etapa_atual or 0,
            etapa=etapa_nome or "",
            mensagem=mensagem,
            status="PAUSADO",
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
        numero_atual, etapa_atual = self._plano_em_execucao()
        etapa_nome = GESTAO_STAGE_LABELS.get(etapa_atual) if etapa_atual else ""
        mensagem = (
            f"Etapa {etapa_atual} retomada" if etapa_atual else "Processamento retomado."
        )
        self._registrar_historico(
            numero_plano=numero_atual,
            progresso=etapa_atual or 0,
            etapa=etapa_nome or "",
            mensagem=mensagem,
            status="RETOMADO",
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
            if await self._run_captura_real():
                return
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
                        status="CONCLUIDO",
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

    def _plano_em_execucao(self) -> tuple[Optional[str], Optional[int]]:
        if not self._status.em_progresso:
            return None, None
        numero, info = next(iter(self._status.em_progresso.items()))
        total_etapas = len(info.etapas or [])
        etapa_atual = info.progresso + 1
        if total_etapas:
            etapa_atual = max(1, min(etapa_atual, total_etapas))
        else:
            etapa_atual = info.progresso if info.progresso > 0 else None
        return numero, etapa_atual

    def _registrar_historico(
        self,
        *,
        numero_plano: Optional[str],
        progresso: int,
        etapa: str,
        mensagem: str,
        status: str = "INFO",
    ) -> None:
        self._ensure_history_loaded()
        timestamp_dt = datetime.now(timezone.utc)
        timestamp = timestamp_dt.isoformat()
        etapa_numero = infer_gestao_stage_numero(etapa, progresso)
        etapa_nome = GESTAO_STAGE_LABELS.get(etapa_numero)
        status_norm = (status or "INFO").upper()
        numero_norm = (numero_plano or "").strip()
        evento = PlanoHistorico(
            numero_plano=numero_norm,
            mensagem=mensagem,
            progresso=progresso,
            etapa=etapa,
            timestamp=timestamp,
            status=status_norm,
            etapa_nome=etapa_nome,
        )
        persist_args = (
            numero_norm or None,
            mensagem,
            status_norm,
            etapa_numero,
            etapa_nome,
            timestamp_dt,
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            loop.create_task(self._persistir_historico_async(*persist_args))
        else:
            self._persistir_historico_sync(*persist_args)

        historico = self._status.historico
        historico.append(evento)
        if len(historico) > self._history_limit:
            del historico[: len(historico) - self._history_limit]
        self._status.ultima_atualizacao = timestamp

    async def _persistir_historico_async(
        self,
        numero_plano: Optional[str],
        mensagem: str,
        status: str,
        etapa_numero: Optional[int],
        etapa_nome: Optional[str],
        created_at: datetime,
    ) -> bool:
        tentativa = 0
        while True:
            try:
                await asyncio.to_thread(
                    self._persistir_historico_once,
                    numero_plano,
                    mensagem,
                    status,
                    etapa_numero,
                    etapa_nome,
                    created_at,
                )
                return True
            except OperationalError as exc:
                mensagem_erro = str(exc).lower()
                if "database is locked" in mensagem_erro and tentativa < 4:
                    tentativa += 1
                    espera = min(0.5, 0.1 * tentativa)
                    logger.warning(
                        "banco bloqueado ao registrar histórico; aguardando %.2fs (tentativa %s)",
                        espera,
                        tentativa,
                    )
                    await asyncio.sleep(espera)
                    continue
                logger.exception("erro ao persistir histórico da captura")
                return False
            except Exception:
                logger.exception("erro ao persistir histórico da captura")
                return False

    def _persistir_historico_sync(
        self,
        numero_plano: Optional[str],
        mensagem: str,
        status: str,
        etapa_numero: Optional[int],
        etapa_nome: Optional[str],
        created_at: datetime,
    ) -> bool:
        tentativa = 0
        while True:
            try:
                self._persistir_historico_once(
                    numero_plano,
                    mensagem,
                    status,
                    etapa_numero,
                    etapa_nome,
                    created_at,
                )
                return True
            except OperationalError as exc:
                mensagem_erro = str(exc).lower()
                if "database is locked" in mensagem_erro and tentativa < 4:
                    tentativa += 1
                    espera = min(0.5, 0.1 * tentativa)
                    logger.warning(
                        "banco bloqueado ao registrar histórico; aguardando %.2fs (tentativa %s)",
                        espera,
                        tentativa,
                    )
                    time.sleep(espera)
                    continue
                logger.exception("erro ao persistir histórico da captura")
                return False
            except Exception:
                logger.exception("erro ao persistir histórico da captura")
                return False

    def _persistir_historico_once(
        self,
        numero_plano: Optional[str],
        mensagem: str,
        status: str,
        etapa_numero: Optional[int],
        etapa_nome: Optional[str],
        created_at: datetime,
    ) -> None:
        with SessionLocal() as db:
            repo = PlanLogRepository(db)
            repo.add(
                contexto="gestao",
                numero_plano=numero_plano,
                mensagem=mensagem,
                status=status,
                etapa_numero=etapa_numero,
                etapa_nome=etapa_nome,
                created_at=created_at,
            )
            db.commit()

    def _ensure_history_loaded(self) -> None:
        if self._history_loaded:
            return
        retry_at = self._history_retry_at
        if retry_at and datetime.now(timezone.utc) < retry_at:
            return
        try:
            with SessionLocal() as db:
                repo = PlanLogRepository(db)
                eventos = repo.recentes(
                    limit=self._history_limit,
                    contexto="gestao",
                    order="desc",
                )
        except Exception:
            logger.exception("erro ao carregar histórico da captura")
            self._history_retry_at = datetime.now(timezone.utc) + timedelta(seconds=5)
            return

        historico: List[PlanoHistorico] = []
        for ev in reversed(eventos):
            timestamp_dt = ev.created_at
            if timestamp_dt and timestamp_dt.tzinfo is None:
                timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
            ts = timestamp_dt.isoformat() if timestamp_dt else None
            historico.append(
                PlanoHistorico(
                    numero_plano=ev.numero_plano or "",
                    mensagem=ev.mensagem,
                    progresso=ev.etapa_numero or 0,
                    etapa=ev.etapa_nome or "",
                    timestamp=ts or datetime.now(timezone.utc).isoformat(),
                    status=ev.status or "INFO",
                    etapa_nome=ev.etapa_nome,
                )
            )
        self._status.historico = historico
        if historico:
            self._status.ultima_atualizacao = historico[-1].timestamp
        self._history_loaded = True
        self._history_retry_at = None

    async def _processar_plano(self, numero_plano: str) -> None:
        st = self._status
        try:
            await self._wait_resume()
            st.em_progresso[numero_plano] = PlanoProgresso(numero_plano, 0)
            cnpj = self._gerar_cnpj()
            saldo = round(random.uniform(1_000, 150_000), 2)
            hoje: date = datetime.now(timezone.utc).date()
            tipo = random.choice(TIPOS_REPRESENTACAO)

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
                    status="DESCARTADO",
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
                    status="DESCARTADO",
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
                    status="DESCARTADO",
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
                    status="DESCARTADO",
                )
                await self._wait_resume()
                st.falhas += 1
                st.processados += 1
                return

            await self._wait_resume()
            with SessionLocal() as db:
                plans = PlanRepository(db)
                events = EventRepository(db)
                razao_social = gerar_razao_social()
                p = plans.upsert(
                    numero_plano=numero_plano,
                    gifug="MZ",
                    situacao_atual="P.RESC.",
                    situacao_anterior="P.RESC.",
                    dias_em_atraso=random.randint(90, 120),
                    tipo=tipo,
                    dt_situacao_atual=hoje,
                    dt_proposta=hoje - timedelta(days=random.randint(30, 180)),
                    saldo=saldo,
                    cmb_ajuste="",
                    justificativa="",
                    matricula="",
                    dt_parcela_atraso=None,
                    representacao=cnpj,
                    numero_inscricao=cnpj,
                    resolucao=random.choice(["123/45", "456/78", "910/11"]),
                    status=PlanStatus.PASSIVEL_RESC,
                    razao_social=razao_social,
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
                status="SUCESSO",
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
                status="FALHA",
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

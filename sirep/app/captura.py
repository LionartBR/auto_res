from __future__ import annotations
import asyncio, random, traceback, logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import List, Dict, Optional, Literal

from sirep.infra.db import SessionLocal
from sirep.infra.repositories import PlanRepository, EventRepository, OccurrenceRepository
from sirep.domain.enums import PlanStatus, Step

logger = logging.getLogger(__name__)

Estado = Literal["ocioso", "executando", "pausado", "concluido"]
TIPOS = ("ADM", "INS", "JUD", "AI", "AJ")
SITS_ALT = ("SIT ESPECIAL", "LIQUIDADO", "RESCINDIDO", "GRDE Emitida")

@dataclass
class PlanoProgresso:
    numero_plano: str
    progresso: int = 0
    etapas: List[str] = field(default_factory=lambda: ["Captura","Situação especial","Liquidação anterior","GRDE"])

@dataclass
class CapturaStatus:
    estado: Estado = "ocioso"
    processados: int = 0
    novos: int = 0
    falhas: int = 0
    em_progresso: Dict[str, PlanoProgresso] = field(default_factory=dict)
    ultima_atualizacao: Optional[str] = None
    last_error: Optional[str] = None  # <<< surfaced

class CapturaService:
    def __init__(self) -> None:
        self._status = CapturaStatus()
        self._loop_task: Optional[asyncio.Task] = None
        self._pause_evt = asyncio.Event(); self._pause_evt.set()
        self._stop_evt = asyncio.Event()
        self._total_alvos = 50
        self._velocidade = 1
        self._step_min = 0.40
        self._step_max = 0.80

    def status(self) -> CapturaStatus: 
        return self._status

    def reset_estado(self) -> None: 
        self._status = CapturaStatus()

    def iniciar(self) -> None:
        if self._status.estado in ("executando", "pausado"):
            logger.info("captura já em %s", self._status.estado)
            return
        self._status = CapturaStatus(estado="executando")
        self._stop_evt = asyncio.Event()
        self._pause_evt.set()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        self._loop_task = loop.create_task(self._run(), name="captura-run")
        logger.info("captura iniciada")

    def pausar(self) -> None:
        if self._status.estado != "executando":
            return
        self._status.estado = "pausado"
        self._pause_evt.clear()
        logger.info("captura pausada")

    def continuar(self) -> None:
        if self._status.estado != "pausado":
            return
        self._status.estado = "executando"
        self._pause_evt.set()
        logger.info("captura continuada")

    async def _run(self) -> None:
        try:
            alvo, gerados = self._total_alvos, 0
            while not self._stop_evt.is_set() and gerados < alvo:
                await self._pause_evt.wait()
                for _ in range(min(self._velocidade, alvo - gerados)):
                    numero = self._gerar_numero()
                    try:
                        asyncio.get_running_loop().create_task(
                            self._processar_plano(numero), name=f"plano-{numero}"
                        )
                    except Exception:
                        self._status.last_error = traceback.format_exc()
                        logger.exception("erro ao criar task do plano %s", numero)
                    gerados += 1
                await asyncio.sleep(1.0)

            while self._status.estado != "pausado" and any(p.progresso < 4 for p in self._status.em_progresso.values()):
                await asyncio.sleep(0.2)

        except Exception:
            self._status.last_error = traceback.format_exc()
            logger.exception("erro no loop principal da captura")
        finally:
            if self._status.estado != "pausado":
                self._status.estado = "concluido"
            logger.info("captura finalizada: %s", self._status.estado)

    async def _processar_plano(self, numero_plano: str) -> None:
        st = self._status
        try:
            st.em_progresso[numero_plano] = PlanoProgresso(numero_plano, 0)
            cnpj = self._gerar_cnpj()
            saldo = round(random.uniform(1_000, 150_000), 2)
            hoje: date = datetime.now(timezone.utc).date()
            tipo = random.choice(TIPOS)

            await asyncio.sleep(random.uniform(self._step_min, self._step_max))
            st.em_progresso[numero_plano].progresso = 1

            await asyncio.sleep(random.uniform(self._step_min, self._step_max))
            if random.random() < 0.10:
                with SessionLocal() as db:
                    OccurrenceRepository(db).add(
                        numero_plano=numero_plano, situacao="SIT ESPECIAL", cnpj=cnpj,
                        tipo=tipo, saldo=saldo, dt_situacao_atual=hoje
                    ); db.commit()
                st.falhas += 1; st.processados += 1
                return
            st.em_progresso[numero_plano].progresso = 2

            await asyncio.sleep(random.uniform(self._step_min, self._step_max))
            if random.random() < 0.08:
                sit = random.choice(("LIQUIDADO","RESCINDIDO"))
                with SessionLocal() as db:
                    OccurrenceRepository(db).add(
                        numero_plano=numero_plano, situacao=sit, cnpj=cnpj,
                        tipo=tipo, saldo=saldo, dt_situacao_atual=hoje
                    ); db.commit()
                st.falhas += 1; st.processados += 1
                return
            st.em_progresso[numero_plano].progresso = 3

            await asyncio.sleep(random.uniform(self._step_min, self._step_max))
            if random.random() < 0.12:
                with SessionLocal() as db:
                    OccurrenceRepository(db).add(
                        numero_plano=numero_plano, situacao="GRDE Emitida", cnpj=cnpj,
                        tipo=tipo, saldo=saldo, dt_situacao_atual=hoje
                    ); db.commit()
                st.falhas += 1; st.processados += 1
                return
            st.em_progresso[numero_plano].progresso = 4

            situacao_final = "P. RESC" if random.random() >= 0.05 else random.choice(SITS_ALT)
            with SessionLocal() as db:
                plans = PlanRepository(db); events = EventRepository(db)
                p = plans.upsert(
                    numero_plano=numero_plano,
                    gifug="MZ",
                    situacao_atual=situacao_final,
                    situacao_anterior="P. RESC",
                    dias_em_atraso=random.randint(90, 120),
                    tipo=tipo,
                    dt_situacao_atual=hoje,
                    saldo=saldo,
                    cmb_ajuste="", justificativa="", matricula="",
                    dt_parcela_atraso=None, representacao="",
                    status=PlanStatus.PASSIVEL_RESC,
                    tipo_parcelamento=tipo, saldo_total=saldo,
                )
                events.log(p.id, Step.ETAPA_1, "Capturado via simulação")
                db.commit()

            st.novos += 1; st.processados += 1

        except Exception:
            st.falhas += 1
            st.last_error = traceback.format_exc()
            logger.exception("erro ao processar plano %s", numero_plano)
        finally:
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
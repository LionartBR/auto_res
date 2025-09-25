from __future__ import annotations

import asyncio
import logging
import random
import re
import string
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional, Literal, Sequence

from sqlalchemy import select

from sirep.app.async_loop import AsyncLoopMixin
from sirep.domain.enums import PlanStatus
from sirep.domain.models import Plan, TreatmentPlan
from sirep.domain.schemas import PlanOut
from sirep.infra.db import SessionLocal
from sirep.infra.repositories import (
    PlanRepository,
    TreatmentPlanRepository,
    PlanLogRepository,
    OccurrenceRepository,
)
from sirep.domain.logs import (
    TRATAMENTO_STAGE_DEFINITIONS,
    TRATAMENTO_STAGE_LABELS,
)
from sirep.shared.config import DATE_DISPLAY_FORMAT
from sirep.shared.fakes import (
    TIPOS_PARCELAMENTO,
    TIPOS_REPRESENTACAO,
    gerar_bases,
    gerar_cnpjs,
    gerar_periodo,
    gerar_razao_social,
)

logger = logging.getLogger(__name__)

EstadoTratamento = Literal["ocioso", "aguardando", "processando", "pausado"]

STAGES = list(TRATAMENTO_STAGE_DEFINITIONS.items())

class TratamentoService(AsyncLoopMixin):
    _ASYNC_LOOP_THREAD_NAME = "tratamento-loop"

    def __init__(self) -> None:
        super().__init__()
        self._estado: EstadoTratamento = "ocioso"
        self._worker_task: Optional[asyncio.Future] = None
        self._queue: Optional[asyncio.Queue[int]] = None
        self._queue_shadow: List[int] = []
        self._current_id: Optional[int] = None
        self._lock = threading.Lock()
        self._active_event: Optional[asyncio.Event] = None
        self._processing_enabled = False

    # ---- infra auxiliar ----
    def _on_loop_ready(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._queue is None:
            self._queue = asyncio.Queue()

    # ---- status público ----
    def estado(self) -> EstadoTratamento:
        with self._lock:
            if self._estado == "pausado":
                return "pausado"
            if self._current_id is not None:
                return "processando"
            if self._queue_shadow:
                return "aguardando"
            return self._estado

    # ---- seed mocks ----
    def seed_planos(self, quantidade: int = 3) -> List[int]:
        created_ids: List[int] = []
        with SessionLocal() as db:
            plans_repo = PlanRepository(db)
            treatment_repo = TreatmentPlanRepository(db)

            for _ in range(quantidade):
                numero = self._gerar_numero_plano(db)
                razao = gerar_razao_social()
                periodo = gerar_periodo()
                cnpjs = gerar_cnpjs()
                bases = gerar_bases()
                tipo = random.choice(TIPOS_PARCELAMENTO)
                principal_cnpj = cnpjs[0]

                plan = plans_repo.upsert(
                    numero_plano=numero,
                    gifug=random.choice(["RJ", "SP", "MG", "BA", "RS"]),
                    situacao_atual="P.RESC.",
                    situacao_anterior="P.RESC.",
                    dias_em_atraso=random.randint(30, 180),
                    tipo=tipo,
                    dt_situacao_atual=date.today() - timedelta(days=random.randint(10, 90)),
                    saldo=float(random.randint(5_000, 60_000)),
                    status=PlanStatus.PASSIVEL_RESC,
                    razao_social=razao,
                    representacao=principal_cnpj,
                    numero_inscricao=principal_cnpj,
                )
                plan.dt_proposta = date.today() - timedelta(days=random.randint(30, 180))
                plan.resolucao = random.choice(["123/45", "987/65", "321/09"])
                plan.cmb_ajuste = ""
                plan.justificativa = ""
                plan.matricula = ""
                plan.dt_parcela_atraso = None
                plan.representacao = principal_cnpj
                plan.data_rescisao = None
                plan.data_comunicacao = None
                plan.metodo_comunicacao = None
                plan.referencia_comunicacao = None

                notas = {
                    "PLANO": numero,
                    "CNPJ_CEI": ", ".join(cnpjs),
                    "RAZAO_SOCIAL": razao,
                    "E544_TIPO": tipo,
                    "E544_PERIODO": periodo,
                    "E544_CNPJS": "\n".join(cnpjs),
                    "E398_BASES": "\n".join(bases),
                }

                treatment = self._criar_tratamento(
                    treatment_repo=treatment_repo,
                    plan=plan,
                    razao=razao,
                    periodo=periodo,
                    cnpjs=cnpjs,
                    bases=bases,
                    notas=notas,
                )
                created_ids.append(treatment.id)

            db.commit()

        if created_ids:
            loop = self._ensure_loop()
            self._start_worker(loop)
            for treatment_id in created_ids:
                self._enqueue(treatment_id, loop=loop)
        return created_ids

    def _gerar_numero_plano(self, db_session) -> str:
        plans_repo = PlanRepository(db_session)
        while True:
            numero = f"TP{random.randint(100000, 999999)}"
            if not plans_repo.get_by_numero(numero):
                return numero

    def _criar_tratamento(
        self,
        *,
        treatment_repo: TreatmentPlanRepository,
        plan,
        razao: str,
        periodo: str,
        cnpjs: List[str],
        bases: List[str],
        notas: dict,
    ) -> TreatmentPlan:
        etapas = [
            {
                "id": sid,
                "nome": nome,
                "status": "pendente",
                "iniciado_em": None,
                "finalizado_em": None,
                "mensagem": "",
            }
            for sid, nome in STAGES
        ]

        treatment = TreatmentPlan(
            plan_id=plan.id,
            numero_plano=plan.numero_plano,
            razao_social=razao,
            status="pendente",
            etapa_atual=0,
            periodo=periodo,
            cnpjs=cnpjs,
            notas=notas,
            etapas=etapas,
            bases=bases,
        )
        treatment_repo.add(treatment)
        return treatment

    def migrar_planos(self) -> List[int]:
        created_ids: List[int] = []
        queue_ids: List[int] = []
        with SessionLocal() as db:
            plans_repo = PlanRepository(db)
            treatment_repo = TreatmentPlanRepository(db)
            occurrence_repo = OccurrenceRepository(db)

            self._materializar_planos_de_ocorrencias(
                plans_repo=plans_repo,
                occurrence_repo=occurrence_repo,
            )

            planos = plans_repo.list_all()
            for plan in planos:
                if treatment_repo.by_plan_id(plan.id):
                    continue

                razao = plan.razao_social or gerar_razao_social()
                if not plan.razao_social:
                    plan.razao_social = razao

                periodo = gerar_periodo()
                cnpjs = gerar_cnpjs()
                bases = gerar_bases()
                tipo = plan.tipo or random.choice(TIPOS_PARCELAMENTO)
                plan.tipo = plan.tipo or tipo
                if not plan.representacao and cnpjs:
                    plan.representacao = cnpjs[0]

                notas = {
                    "PLANO": plan.numero_plano,
                    "CNPJ_CEI": ", ".join(cnpjs),
                    "RAZAO_SOCIAL": razao,
                    "E544_TIPO": tipo,
                    "E544_PERIODO": periodo,
                    "E544_CNPJS": "\n".join(cnpjs),
                    "E398_BASES": "\n".join(bases),
                }

                treatment = self._criar_tratamento(
                    treatment_repo=treatment_repo,
                    plan=plan,
                    razao=razao,
                    periodo=periodo,
                    cnpjs=cnpjs,
                    bases=bases,
                    notas=notas,
                )

                status_raw = plan.status or ""
                plan_status: Optional[PlanStatus] = None
                if status_raw:
                    try:
                        plan_status = PlanStatus(status_raw)
                    except ValueError:
                        plan_status = None

                should_queue = plan_status in {
                    PlanStatus.PASSIVEL_RESC,
                    PlanStatus.NOVO,
                    PlanStatus.SEM_TRATAMENTO,
                }

                if plan_status == PlanStatus.RESCINDIDO:
                    treatment.status = "rescindido"
                    if plan.data_rescisao:
                        treatment.rescisao_data = plan.data_rescisao
                elif plan_status in {
                    PlanStatus.LIQUIDADO,
                    PlanStatus.NAO_RESCINDIDO,
                    PlanStatus.ESPECIAL,
                }:
                    treatment.status = status_raw
                elif not should_queue and status_raw:
                    treatment.status = status_raw

                if plan.data_rescisao and treatment.rescisao_data is None:
                    treatment.rescisao_data = plan.data_rescisao

                created_ids.append(treatment.id)
                if should_queue:
                    queue_ids.append(treatment.id)

            db.commit()

        if queue_ids:
            loop = self._ensure_loop()
            self._start_worker(loop)
            for treatment_id in queue_ids:
                self._enqueue(treatment_id, loop=loop)
        return created_ids

    def _materializar_planos_de_ocorrencias(
        self,
        *,
        plans_repo: PlanRepository,
        occurrence_repo: OccurrenceRepository,
    ) -> None:
        ocorrencias = occurrence_repo.list_all()
        for ocorrencia in ocorrencias:
            numero = (ocorrencia.numero_plano or "").strip()
            if not numero:
                continue

            plan = plans_repo.get_by_numero(numero)
            if plan is not None:
                continue

            campos: dict[str, Any] = {}
            situacao = (ocorrencia.situacao or "").strip()
            if situacao:
                campos["situacao_atual"] = situacao
                campos["status"] = self._status_por_situacao(situacao)
            if ocorrencia.tipo:
                campos["tipo"] = ocorrencia.tipo
            if ocorrencia.saldo is not None:
                campos["saldo"] = ocorrencia.saldo
            if ocorrencia.dt_situacao_atual:
                campos["dt_situacao_atual"] = ocorrencia.dt_situacao_atual

            representacao = (ocorrencia.cnpj or "").strip()
            inscricao = self._somente_digitos(representacao)
            if representacao:
                campos["representacao"] = representacao
            if inscricao:
                campos["numero_inscricao"] = inscricao

            plans_repo.upsert(numero_plano=numero, **campos)

    @staticmethod
    def _somente_digitos(valor: str | None) -> str | None:
        if not valor:
            return None
        digits = re.sub(r"\D", "", valor)
        return digits or None

    @staticmethod
    def _status_por_situacao(situacao: str | None) -> PlanStatus:
        texto = (situacao or "").strip().upper()
        if not texto:
            return PlanStatus.PASSIVEL_RESC
        if texto.startswith("P.RESC") or texto.startswith("PRESC"):
            return PlanStatus.PASSIVEL_RESC
        if "ESPECIAL" in texto:
            return PlanStatus.ESPECIAL
        if "LIQ" in texto:
            return PlanStatus.LIQUIDADO
        if "GRDE" in texto:
            return PlanStatus.NAO_RESCINDIDO
        if texto.startswith("RESC"):
            return PlanStatus.RESCINDIDO
        return PlanStatus.PASSIVEL_RESC

    # ---- controle de execução ----
    def iniciar(self) -> None:
        loop = self._ensure_loop()
        with self._lock:
            self._processing_enabled = True
            if self._current_id is not None:
                self._estado = "processando"
            elif self._queue_shadow:
                self._estado = "aguardando"
            else:
                self._estado = "ocioso"
        self._start_worker(loop)

    def pausar(self) -> None:
        with self._lock:
            if self._estado not in ("processando", "aguardando"):
                return
            self._processing_enabled = False
            self._estado = "pausado"
            event = self._active_event
        if event is not None:
            self._run_on_loop(event.clear)
        with SessionLocal() as db:
            plan_repo = TreatmentPlanRepository(db)
            log_repo = PlanLogRepository(db)
            treatment = plan_repo.get(self._current_id) if self._current_id else None
            etapa_atual = treatment.etapa_atual if treatment else None
            etapa_nome = TRATAMENTO_STAGE_LABELS.get(etapa_atual) if etapa_atual else ""
            mensagem = (
                f"Etapa {etapa_atual} pausada" if etapa_atual else "Fila de tratamento pausada."
            )
            log_repo.add(
                contexto="tratamento",
                treatment_id=treatment.id if treatment else None,
                numero_plano=treatment.numero_plano if treatment else None,
                etapa_numero=etapa_atual,
                etapa_nome=etapa_nome,
                status="PAUSADO",
                mensagem=mensagem,
            )
            db.commit()

    def continuar(self) -> None:
        self._restore_pending_queue()
        loop = self._ensure_loop()
        with self._lock:
            if self._estado != "pausado":
                return
            self._processing_enabled = True
            if self._current_id is not None:
                self._estado = "processando"
            elif self._queue_shadow:
                self._estado = "aguardando"
            else:
                self._estado = "ocioso"
            event = self._active_event
        self._start_worker(loop)
        if event is not None:
            self._run_on_loop(event.set, loop=loop)
        with SessionLocal() as db:
            plan_repo = TreatmentPlanRepository(db)
            log_repo = PlanLogRepository(db)
            treatment = plan_repo.get(self._current_id) if self._current_id else None
            etapa_atual = treatment.etapa_atual if treatment else None
            etapa_nome = TRATAMENTO_STAGE_LABELS.get(etapa_atual) if etapa_atual else ""
            mensagem = (
                f"Etapa {etapa_atual} retomada" if etapa_atual else "Fila de tratamento retomada."
            )
            log_repo.add(
                contexto="tratamento",
                treatment_id=treatment.id if treatment else None,
                numero_plano=treatment.numero_plano if treatment else None,
                etapa_numero=etapa_atual,
                etapa_nome=etapa_nome,
                status="RETOMADO",
                mensagem=mensagem,
            )
            db.commit()

    async def _wait_resume(self) -> None:
        while True:
            event = self._active_event
            if event is None:
                return
            if event.is_set():
                return
            await event.wait()

    async def _sleep_with_pause(self, duration: float) -> None:
        remaining = duration
        while remaining > 0:
            await self._wait_resume()
            interval = min(0.2, remaining)
            await asyncio.sleep(interval)
            event = self._active_event
            if event is not None and not event.is_set():
                continue
            remaining -= interval

    def _start_worker(self, loop: asyncio.AbstractEventLoop) -> None:
        def ensure_worker() -> None:
            if self._active_event is None:
                self._active_event = asyncio.Event()
            if self._processing_enabled:
                self._active_event.set()
            else:
                self._active_event.clear()
            if self._worker_task is None or getattr(self._worker_task, "done", lambda: True)():
                self._worker_task = loop.create_task(self._run(), name="tratamento-run")

        self._run_on_loop(ensure_worker, wait=True, loop=loop)

    def _enqueue(self, treatment_id: int, *, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        loop = loop or self._ensure_loop()

        def push() -> None:
            if self._queue is None:
                raise RuntimeError("fila de tratamento não inicializada")
            self._queue.put_nowait(treatment_id)
            with self._lock:
                self._queue_shadow.append(treatment_id)
                if self._current_id is None and self._estado != "pausado":
                    self._estado = "aguardando"

        self._run_on_loop(push, loop=loop)

    async def _run(self) -> None:
        if self._queue is None:
            self._queue = asyncio.Queue()
        while True:
            treatment_id = await self._queue.get()
            await self._wait_resume()
            with self._lock:
                if treatment_id in self._queue_shadow:
                    self._queue_shadow.remove(treatment_id)
                self._current_id = treatment_id
                if self._estado != "pausado":
                    self._estado = "processando"
            try:
                await self._process_plan(treatment_id)
            except Exception:
                logger.exception("Falha ao processar tratamento %s", treatment_id)
            finally:
                with self._lock:
                    self._current_id = None
                    if self._queue_shadow:
                        if self._processing_enabled:
                            self._estado = "aguardando"
                        else:
                            self._estado = "pausado"
                    else:
                        self._estado = "ocioso"
                        self._processing_enabled = False
                        if self._active_event is not None:
                            self._active_event.clear()
                self._queue.task_done()

    def _pending_ids_from_planos(self, planos: Sequence[TreatmentPlan]) -> List[int]:
        prioridade = [plano.id for plano in planos if plano.status == "processando"]
        pendentes = [plano.id for plano in planos if plano.status == "pendente"]
        ordem = prioridade + pendentes
        # Remove duplicados preservando ordem
        return list(dict.fromkeys(ordem))

    def _restore_pending_ids(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        loop = self._ensure_loop()

        def sync() -> None:
            if self._queue is None:
                self._queue = asyncio.Queue()
            added_any = False
            with self._lock:
                existing = set(self._queue_shadow)
                if self._current_id is not None:
                    existing.add(self._current_id)
                for pid in ids:
                    if pid in existing:
                        continue
                    self._queue.put_nowait(pid)
                    self._queue_shadow.append(pid)
                    existing.add(pid)
                    added_any = True
                if added_any and not self._processing_enabled:
                    self._estado = "pausado"

        self._run_on_loop(sync, wait=True, loop=loop)

    def _restore_pending_queue(self, planos: Optional[Sequence[TreatmentPlan]] = None) -> None:
        if planos is None:
            with SessionLocal() as db:
                repo = TreatmentPlanRepository(db)
                planos = repo.list_all()
        pending_ids = self._pending_ids_from_planos(planos)
        self._restore_pending_ids(pending_ids)

    # ---- execução das etapas ----
    async def _process_plan(self, treatment_id: int) -> None:
        with SessionLocal() as db:
            treatment_repo = TreatmentPlanRepository(db)
            logs_repo = PlanLogRepository(db)
            plan_repo = PlanRepository(db)

            treatment = treatment_repo.get(treatment_id)
            if treatment is None:
                logger.warning("tratamento %s não encontrado", treatment_id)
                return

            # garante campos básicos
            treatment.status = "processando"
            db.commit()

            for stage_id, stage_nome in STAGES:
                stage_data = self._buscar_stage(treatment, stage_id)
                if stage_data.get("status") in {"concluido", "cancelado"}:
                    continue
                await self._wait_resume()
                self._marcar_inicio_etapa(treatment, stage_id)
                etapa_label = TRATAMENTO_STAGE_LABELS.get(stage_id)
                logs_repo.add(
                    contexto="tratamento",
                    treatment_id=treatment.id,
                    numero_plano=treatment.numero_plano,
                    etapa_numero=stage_id,
                    etapa_nome=etapa_label,
                    status="INICIO",
                    mensagem=f"Iniciada {stage_nome}",
                )
                db.commit()

                await self._sleep_with_pause(random.uniform(4.0, 7.0))
                await self._wait_resume()

                resultado = self._executar_etapa(
                    db=db,
                    plan_repo=plan_repo,
                    logs_repo=logs_repo,
                    treatment=treatment,
                    stage_id=stage_id,
                    stage_nome=stage_nome,
                )

                db.commit()

                if resultado == "descartado":
                    break

            db.refresh(treatment)
            if treatment.status not in ("rescindido", "descartado"):
                treatment.status = "rescindido"
                treatment.etapa_atual = 7
                self._marcar_conclusao_etapa(treatment, 7, "Comunicação concluída")
                db.commit()

    def _executar_etapa(self, *, db, plan_repo, logs_repo, treatment: TreatmentPlan, stage_id: int, stage_nome: str) -> Optional[str]:
        etapa_label = TRATAMENTO_STAGE_LABELS.get(stage_id)
        if stage_id == 1:
            self._etapa1(treatment)
            mensagem = "Dados de aproveitamento registrados"
        elif stage_id == 2:
            self._etapa2(treatment)
            mensagem = "Análise de substituição concluída"
        elif stage_id == 3:
            self._etapa3(treatment)
            mensagem = "Pesquisa de guias registrada"
        elif stage_id == 4:
            self._etapa4(treatment)
            mensagem = "Lançamento de guias concluído"
        elif stage_id == 5:
            resultado = self._etapa5(treatment)
            if resultado == "descartado":
                logs_repo.add(
                    contexto="tratamento",
                    treatment_id=treatment.id,
                    numero_plano=treatment.numero_plano,
                    etapa_numero=stage_id,
                    etapa_nome=etapa_label,
                    status="DESCARTADO",
                    mensagem="Plano descartado após revalidação",
                )
                self._marcar_conclusao_etapa(treatment, stage_id, "Plano descartado")
                db.commit()
                treatment.status = "descartado"
                self._marcar_cancelamento_restante(treatment, apartir=stage_id + 1)
                return "descartado"
            mensagem = "Situação do plano validada"
        elif stage_id == 6:
            self._etapa6(treatment, plan_repo)
            mensagem = "Plano atualizado para RESCINDIDO"
        elif stage_id == 7:
            self._etapa7(treatment, plan_repo)
            mensagem = "Comunicação registrada"
        else:
            mensagem = "Etapa desconhecida"

        logs_repo.add(
            contexto="tratamento",
            treatment_id=treatment.id,
            numero_plano=treatment.numero_plano,
            etapa_numero=stage_id,
            etapa_nome=etapa_label,
            status="SUCESSO",
            mensagem=mensagem,
        )
        self._marcar_conclusao_etapa(treatment, stage_id, mensagem)
        return None

    def _marcar_inicio_etapa(self, treatment: TreatmentPlan, stage_id: int) -> None:
        stage = self._buscar_stage(treatment, stage_id)
        agora = datetime.now(timezone.utc).isoformat()
        stage["status"] = "processando"
        stage["iniciado_em"] = stage.get("iniciado_em") or agora
        stage["mensagem"] = ""
        treatment.etapa_atual = stage_id

    def _marcar_conclusao_etapa(self, treatment: TreatmentPlan, stage_id: int, mensagem: str) -> None:
        stage = self._buscar_stage(treatment, stage_id)
        stage["status"] = "concluido"
        stage["finalizado_em"] = datetime.now(timezone.utc).isoformat()
        stage["mensagem"] = mensagem

    def _marcar_cancelamento_restante(self, treatment: TreatmentPlan, apartir: int) -> None:
        for sid, _ in STAGES:
            if sid >= apartir:
                stage = self._buscar_stage(treatment, sid)
                if stage["status"] != "concluido":
                    stage["status"] = "cancelado"
                    stage["mensagem"] = "Etapa não executada por descarte"

    def _buscar_stage(self, treatment: TreatmentPlan, stage_id: int) -> dict:
        for stage in treatment.etapas:
            if stage["id"] == stage_id:
                return stage
        nome = dict(STAGES).get(stage_id, f"Etapa {stage_id}")
        stage = {
            "id": stage_id,
            "nome": nome,
            "status": "pendente",
            "iniciado_em": None,
            "finalizado_em": None,
            "mensagem": "",
        }
        treatment.etapas.append(stage)
        return stage

    def _etapa1(self, treatment: TreatmentPlan) -> None:
        houve_aproveitamento = random.choice(["Sim", "Não"])
        texto = (
            "CNPJs analisados: "
            + ", ".join(treatment.cnpjs)
            + f"\nPeríodo: {treatment.periodo}\nRazão social: {treatment.razao_social}\nHouve aproveitamento? {houve_aproveitamento}"
        )
        treatment.notas["E213_APROVEITAMENTO_RECOLHIMENTOS"] = texto
        treatment.notas["E544_DATA_SOLICITACAO"] = ""
        treatment.notas.setdefault("E544_PERIODO", treatment.periodo)
        treatment.notas.setdefault("E544_CNPJS", "\n".join(treatment.cnpjs))
        treatment.notas.setdefault("CNPJ_CEI", ", ".join(treatment.cnpjs))
        treatment.notas.setdefault("RAZAO_SOCIAL", treatment.razao_social)
        treatment.notas.setdefault("PLANO", treatment.numero_plano)
        treatment.notas["E398_BASES"] = "\n".join(treatment.bases)

    def _etapa2(self, treatment: TreatmentPlan) -> None:
        has_overlap = random.choice([True, False])
        if has_overlap:
            inicio = date.today() - timedelta(days=random.randint(60, 240))
            fim = inicio + timedelta(days=random.randint(60, 180))
            competencias = f"{inicio.strftime('%m/%Y')} a {fim.strftime('%m/%Y')}"
        else:
            competencias = "Sem competências congruentes"
        houve_substituicao = random.choice([True, False])
        resultado = (
            "Débitos confessados substituídos por notificação fiscal"
            if houve_substituicao
            else "Sem substituição"
        )
        texto = (
            f"Há indícios de competências congruentes? {competencias}"
            f"\nResultado: {resultado}"
        )
        treatment.notas["E206_SUBSTITUICAO_CONFISSAO_NOTIFICACAO"] = texto

    def _etapa3(self, treatment: TreatmentPlan) -> None:
        quantidade = random.randint(0, 5)
        if quantidade == 0:
            texto = "PESQUISA DE GUIAS SFG: NÃO HÁ GUIAS"
        else:
            texto = f"PESQUISA DE GUIAS SFG: {quantidade:02d} GUIAS LOCALIZADAS"
        treatment.notas["PESQUISA_GUIAS_SFG"] = texto

    def _etapa4(self, treatment: TreatmentPlan) -> None:
        quantidade = random.randint(0, 5)
        if quantidade == 0:
            texto = "GUIAS LANÇADAS: NENHUMA GUIA PROCESSADA"
        else:
            texto = f"GUIAS LANÇADAS: {quantidade:02d} GUIAS PROCESSADAS"
        treatment.notas["LANCAMENTO_GUIAS_FGE"] = texto

    def _etapa5(self, treatment: TreatmentPlan) -> Optional[str]:
        data_solicitacao = date.today() - timedelta(days=random.randint(100, 600))
        parcelas = []
        valor_base = random.uniform(350.0, 980.0)
        for idx in range(4, 7):
            valor = f"{valor_base + random.uniform(-40, 40):.2f}".replace(".", ",")
            vencimento = (date.today() + timedelta(days=30 * (idx - 3))).strftime(
                DATE_DISPLAY_FORMAT
            )
            parcelas.append(f"{idx:03d}           {valor}              {vencimento}")
        treatment.notas["E544_DATA_SOLICITACAO"] = data_solicitacao.strftime(
            DATE_DISPLAY_FORMAT
        )
        treatment.notas["E50H_PARCELAS_ATRASO"] = "\n".join(parcelas)

        if random.random() <= 0.01:
            return "descartado"
        return None

    def _etapa6(self, treatment: TreatmentPlan, plan_repo: PlanRepository) -> None:
        hoje = date.today()
        plan = plan_repo.get_by_numero(treatment.numero_plano)
        if plan is None:
            return
        plan.situacao_atual = "RESCINDIDO"
        plan.dt_situacao_atual = hoje
        plan.status = PlanStatus.RESCINDIDO
        plan.data_rescisao = hoje
        treatment.rescisao_data = hoje
        treatment.notas["E554_DATA_RESCISAO_FGE"] = hoje.strftime(DATE_DISPLAY_FORMAT)

    def _etapa7(self, treatment: TreatmentPlan, plan_repo: PlanRepository) -> None:
        metodo = random.choice(["CNS", "Email"])
        data_comunicacao = date.today()
        if metodo == "CNS":
            ref = "NSU-" + "".join(random.choices(string.digits, k=8))
        else:
            ref = f"contato_{random.randint(100, 999)}@empresa.com"
        treatment.notas["E554_DATA_COMUNICACAO"] = data_comunicacao.strftime(
            DATE_DISPLAY_FORMAT
        )
        treatment.notas["E554_METODO_COMUNICACAO"] = metodo
        treatment.notas["E554_NSU_OU_EMAIL"] = ref
        treatment.notas.setdefault("E554_NOME_DOSSIE", f"Dossie_{treatment.numero_plano}")
        treatment.notas.setdefault(
            "E554_DATA_FINALIZACAO_SIREP",
            date.today().strftime(DATE_DISPLAY_FORMAT),
        )

        plan = plan_repo.get_by_numero(treatment.numero_plano)
        if plan:
            plan.data_comunicacao = data_comunicacao
            plan.metodo_comunicacao = metodo
            plan.referencia_comunicacao = ref

    # ---- consultas ----
    def status(self) -> dict:
        plan_map: dict[int, dict[str, Any]] = {}
        with SessionLocal() as db:
            treatment_repo = TreatmentPlanRepository(db)
            log_repo = PlanLogRepository(db)
            planos = treatment_repo.list_all()
            logs = log_repo.recentes(limit=40, contexto="tratamento")

            plan_ids = {plano.plan_id for plano in planos if plano.plan_id is not None}
            if plan_ids:
                stmt = select(Plan).where(Plan.id.in_(plan_ids))
                plan_rows = db.scalars(stmt).all()
                plan_map = {
                    plan.id: PlanOut.model_validate(plan).model_dump(mode="json")
                    for plan in plan_rows
                }

        self._restore_pending_queue(planos)

        planos_data = []
        for plano in planos:
            plan_info = plan_map.get(plano.plan_id) or {}
            planos_data.append(
                {
                    "id": plano.id,
                    "plan_id": plano.plan_id,
                    "numero_plano": plano.numero_plano,
                    "razao_social": plano.razao_social,
                    "status": plano.status,
                    "etapa_atual": plano.etapa_atual,
                    "periodo": plano.periodo,
                    "cnpjs": plano.cnpjs,
                    "bases": plano.bases,
                    "rescisao_data": plano.rescisao_data.isoformat() if plano.rescisao_data else None,
                    "tipo": plan_info.get("tipo"),
                    "situacao_atual": plan_info.get("situacao_atual"),
                    "dt_situacao_atual": plan_info.get("dt_situacao_atual"),
                    "saldo": plan_info.get("saldo"),
                    "cnpj": plan_info.get("cnpj") or plan_info.get("representacao"),
                    "etapas": plano.etapas,
                }
            )

        logs_data = [
            {
                "id": log.id,
                "treatment_id": log.treatment_id,
                "numero_plano": log.numero_plano,
                "etapa": log.etapa_numero,
                "etapa_nome": log.etapa_nome,
                "status": log.status,
                "mensagem": log.mensagem,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "contexto": log.contexto,
            }
            for log in logs
        ]

        return {
            "estado": self.estado(),
            "atual": self._current_id,
            "fila": list(self._queue_shadow),
            "planos": planos_data,
            "logs": logs_data,
        }


tratamento = TratamentoService()

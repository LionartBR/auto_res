from datetime import datetime
from typing import Iterable, List, Dict, Any

from sirep.domain.enums import PlanStatus, Step
from sirep.infra.repositories import PlanRepository, EventRepository, JobRunRepository
from sirep.shared.idempotency import compute_hash
from sirep.adapters.base import (
    FGEAdapter, SirepAdapter, CEFGDAdapter, CNSAdapter, PIGAdapter
)
from .base import unit_of_work, ServiceResult


class Etapa1Captura:
    """Captura planos P. RESC, exclui 974/20, busca saldo e carrega no SIREP."""
    def __init__(self, fge: FGEAdapter, sirep: SirepAdapter):
        self.fge, self.sirep = fge, sirep

    def execute(self) -> ServiceResult:
        payload = {"step": Step.ETAPA_1}
        h = compute_hash(payload)
        hoje = datetime.utcnow().date()
        with unit_of_work() as db:
            jobs = JobRunRepository(db)
            job = jobs.start(job_name=Step.ETAPA_1, step=Step.ETAPA_1, input_hash=h)
            plans = PlanRepository(db); events = EventRepository(db)
            linhas: List[Dict[str, Any]] = []

            for p in self.fge.listar_planos_presc_sem_974():
                numero = p["numero_plano"]
                tipo = p.get("tipo")
                saldo = self.fge.obter_saldo_total(numero)

                # Linha p/ carga SIREP
                linhas.append({
                    "CARTEIRA": numero,
                    "GIFUG": "MZ",
                    "SITUACAO_ATUAL": "P. RESC",
                    "SITUACAO_ANTERIOR": "P. RESC",
                    "DIAS_EM_ATRASO": "100",
                    "TIPO": tipo,
                    "DT_SITUACAO_ATUAL": hoje.isoformat(),
                    "SALDO": float(saldo),
                    "cmb_AJUSTE": "", "JUSTIFICATIVA": "", "MATRICULA": "",
                    "DT_PARCELA_ATRASO": "", "REPRESENTACAO": "",
                })

                # Registro local
                plan = plans.upsert(
                    numero_plano=numero,
                    gifug="MZ",
                    situacao_atual="P. RESC",
                    situacao_anterior="P. RESC",
                    dias_em_atraso=100,
                    tipo=tipo,
                    dt_situacao_atual=hoje,
                    saldo=saldo,
                    cmb_ajuste="",
                    justificativa="",
                    matricula="",
                    dt_parcela_atraso=None,
                    representacao="",
                    status=PlanStatus.PASSIVEL_RESC,
                    # compat legada
                    tipo_parcelamento=tipo,
                    saldo_total=saldo,
                )
                events.log(plan.id, Step.ETAPA_1, "Capturado plano P. RESC")

            # carga complementar no SIREP
            self.sirep.carga_complementar(linhas)
            jobs.finish(
                job.id,
                status="FINISHED",
                info_update={"summary": f"{len(linhas)} planos"},
            )
            return {"job_id": job.id, "count": len(linhas)}


class Etapa2SituacaoEspecial:
    """Marca planos como ESPECIAL se constarem no CEFGD."""
    def __init__(self, sirep: SirepAdapter, cefgd: CEFGDAdapter):
        self.sirep, self.cefgd = sirep, cefgd

    def execute(self) -> ServiceResult:
        linhas = self.sirep.listar_sem_tratamento()
        afetados = 0
        with unit_of_work() as db:
            plans = PlanRepository(db); events = EventRepository(db); jobs = JobRunRepository(db)
            job = jobs.start(
                job_name=Step.ETAPA_2,
                step=Step.ETAPA_2,
                input_hash=compute_hash(linhas),
            )
            for l in linhas:
                numero = l["numero_plano"]
                if self.cefgd.plano_e_especial(numero):
                    self.sirep.atualizar_plano(numero, {"especial": True})
                    p = plans.upsert(numero, status=PlanStatus.ESPECIAL)
                    events.log(p.id, Step.ETAPA_2, "Plano classificado como especial")
                    afetados += 1
            jobs.finish(
                job.id,
                status="FINISHED",
                info_update={"summary": f"{afetados} especiais"},
            )
            return {"job_id": job.id, "afetados": afetados}


class Etapa3LiquidacaoAnterior:
    """Identifica planos já liquidados/rescindidos anteriormente."""
    def __init__(self, fge: FGEAdapter, sirep: SirepAdapter):
        self.fge, self.sirep = fge, sirep

    def execute(self) -> ServiceResult:
        linhas = self.sirep.listar_sem_tratamento()
        with unit_of_work() as db:
            plans = PlanRepository(db); events = EventRepository(db); jobs = JobRunRepository(db)
            job = jobs.start(
                job_name=Step.ETAPA_3,
                step=Step.ETAPA_3,
                input_hash=compute_hash(linhas),
            )
            for l in linhas:
                numero = l["numero_plano"]
                # Stub: marca alguns como liquidados
                if numero.endswith("1"):
                    self.sirep.atualizar_plano(numero, {"justificativa": "Liquidado anteriormente"})
                    p = plans.upsert(numero, status=PlanStatus.LIQUIDADO)
                    events.log(p.id, Step.ETAPA_3, "Liquidado/rescindido anteriormente")
            jobs.finish(job.id, status="FINISHED")
            return {"job_id": job.id}


class Etapa4GuiaGRDE:
    """Bloqueia planos com GRDE emitida."""
    def __init__(self, fge: FGEAdapter, sirep: SirepAdapter):
        self.fge, self.sirep = fge, sirep

    def execute(self) -> ServiceResult:
        linhas = self.sirep.listar_sem_tratamento()
        with unit_of_work() as db:
            plans = PlanRepository(db); events = EventRepository(db); jobs = JobRunRepository(db)
            job = jobs.start(
                job_name=Step.ETAPA_4,
                step=Step.ETAPA_4,
                input_hash=compute_hash(linhas),
            )
            for l in linhas:
                numero = l["numero_plano"]
                if self.fge.plano_tem_grde(numero):
                    self.sirep.atualizar_plano(numero, {"grde": True, "justificativa": "Existe GRDE"})
                    p = plans.upsert(numero, status=PlanStatus.NAO_RESCINDIDO)
                    events.log(p.id, Step.ETAPA_4, "GRDE emitida")
            jobs.finish(job.id, status="FINISHED")
            return {"job_id": job.id}


class Etapa5AproveitamentoRecolh:
    """Extrai inscrições/competências (stub)."""
    def __init__(self, fge: FGEAdapter):
        self.fge = fge

    def execute(self) -> ServiceResult:
        return {"status": "OK", "dados_extraidos": 2}


class Etapa7SubstituicaoE206:
    """Verifica substituição Confissão→Notificação (E206)."""
    def __init__(self, fge: FGEAdapter, sirep: SirepAdapter):
        self.fge, self.sirep = fge, sirep

    def execute(self) -> ServiceResult:
        with unit_of_work() as db:
            plans = PlanRepository(db); events = EventRepository(db); jobs = JobRunRepository(db)
            ativos = plans.list_by_status(PlanStatus.PASSIVEL_RESC)
            job = jobs.start(
                job_name=Step.ETAPA_7,
                step=Step.ETAPA_7,
                input_hash=compute_hash([p.numero_plano for p in ativos]),
            )
            for p in ativos:
                confessados = self.fge.listar_debitos_confessados(p.numero_plano)
                houve_subst = any(
                    self.fge.consultar_notificado(d["inscricao"], d["competencia"])
                    for d in confessados
                )
                msg = "Débito confessado substituído por notificação fiscal" if houve_subst else "Sem substituição"
                events.log(p.id, Step.ETAPA_7, msg)
            jobs.finish(job.id, status="FINISHED")
            return {"job_id": job.id, "planos": len(ativos)}


class Etapa8PIGPesquisa:
    """Pesquisa de guias no PIG (stub)."""
    def __init__(self, pig: PIGAdapter):
        self.pig = pig

    def execute(self) -> ServiceResult:
        return {"status": "OK", "pesquisas": 1}


class Etapa9PIGLancamento:
    """Lançamento de guias via PIG (stub)."""
    def __init__(self, pig: PIGAdapter):
        self.pig = pig

    def execute(self) -> ServiceResult:
        return {"status": "OK", "lancadas": 1}


class Etapa10SituacaoPlano:
    """Revalida situação do plano (bloqueia se deixou de ser P. RESC)."""
    def __init__(self, fge: FGEAdapter, sirep: SirepAdapter):
        self.fge, self.sirep = fge, sirep

    def execute(self) -> ServiceResult:
        with unit_of_work() as db:
            plans = PlanRepository(db); events = EventRepository(db); jobs = JobRunRepository(db)
            ativos = plans.list_by_status(PlanStatus.PASSIVEL_RESC)
            job = jobs.start(
                job_name=Step.ETAPA_10,
                step=Step.ETAPA_10,
                input_hash=compute_hash([p.numero_plano for p in ativos]),
            )
            for p in ativos:
                # Stub: alterna para não elegível alguns exemplos
                if p.numero_plano.endswith("2"):
                    plans.set_status(p, PlanStatus.NAO_RESCINDIDO)
                    events.log(p.id, Step.ETAPA_10, "Situação alterada – não passível de rescisão")
            jobs.finish(job.id, status="FINISHED")
            return {"job_id": job.id}


class Etapa11Rescisao:
    """Executa rescisão (E554) e gera Rescindidos_CNPJ/CEI.txt (stub)."""
    def __init__(self, fge: FGEAdapter, sirep: SirepAdapter):
        self.fge, self.sirep = fge, sirep

    def execute(self) -> ServiceResult:
        rescindidos_cnpj: List[str] = []
        rescindidos_cei: List[str] = []
        with unit_of_work() as db:
            plans = PlanRepository(db); events = EventRepository(db); jobs = JobRunRepository(db)
            ativos = plans.list_by_status(PlanStatus.PASSIVEL_RESC)
            job = jobs.start(
                job_name=Step.ETAPA_11,
                step=Step.ETAPA_11,
                input_hash=compute_hash([p.numero_plano for p in ativos]),
            )
            for p in ativos:
                ok = self.fge.executar_rescisao(p.numero_plano)
                if ok:
                    plans.set_status(p, PlanStatus.RESCINDIDO)
                    # Stub: sem vínculo real inscrição↔plano
                    rescindidos_cnpj.append("00123456000199")
                    events.log(p.id, Step.ETAPA_11, f"Rescindido em {datetime.utcnow().date().isoformat()}")
                else:
                    events.log(p.id, Step.ETAPA_11, "Falha de rescisão", level="ERROR")
            jobs.finish(job.id, status="FINISHED")

        with open("Rescindidos_CNPJ.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(rescindidos_cnpj))
        with open("Rescindidos_CEI.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(rescindidos_cei))
        return {"Rescindidos_CNPJ": len(rescindidos_cnpj), "Rescindidos_CEI": len(rescindidos_cei)}


class Etapa12Comunicacao:
    """Envia comunicação via CNS (stub), registra NSU por inscrição."""
    def __init__(self, cns: CNSAdapter):
        self.cns = cns

    def execute(self) -> ServiceResult:
        cnpj: List[str] = []
        try:
            with open("Rescindidos_CNPJ.txt", "r", encoding="utf-8") as f:
                cnpj = [l.strip() for l in f if l.strip()]
        except FileNotFoundError:
            return {"status": "SKIPPED", "motivo": "sem rescindidos"}
        recibos = self.cns.enviar_comunicacao(
            inscricoes=cnpj,
            titulo="Rescisão de Parcelamento FGTS",
            corpo="Comunicação institucional de rescisão."
        )
        return {"enviados": len(recibos)}


class Etapa13Dossie:
    """Gera dossiê (stub)."""
    def execute(self) -> ServiceResult:
        return {"pasta": "Rescisao_Parcelamentos_YYYY_MM_DD", "relatorios": 2}

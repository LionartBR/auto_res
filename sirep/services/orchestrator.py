from typing import Dict, Any, List
from sirep.domain.enums import Step
from sirep.adapters.stubs import FGEStub, SirepStub, CNSStub, PIGStub
from sirep.services.gestao_base import GestaoBaseNoOpService, GestaoBaseService
from .etapas import (
    Etapa5AproveitamentoRecolh, Etapa7SubstituicaoE206, Etapa8PIGPesquisa,
    Etapa9PIGLancamento, Etapa10SituacaoPlano, Etapa11Rescisao, Etapa12Comunicacao,
    Etapa13Dossie
)

class Orchestrator:
    def __init__(self):
        # Substitua stubs por adapters reais quando prontos.
        self.fge, self.sirep, self.cns, self.pig = FGEStub(), SirepStub(), CNSStub(), PIGStub()
        self.gestao_base = GestaoBaseService()
        self.noop_etapa2 = GestaoBaseNoOpService(Step.ETAPA_2)
        self.noop_etapa3 = GestaoBaseNoOpService(Step.ETAPA_3)
        self.noop_etapa4 = GestaoBaseNoOpService(Step.ETAPA_4)
        self.map = {
            Step.ETAPA_1: self.gestao_base,
            Step.ETAPA_2: self.noop_etapa2,
            Step.ETAPA_3: self.noop_etapa3,
            Step.ETAPA_4: self.noop_etapa4,
            Step.ETAPA_5: Etapa5AproveitamentoRecolh(self.fge),
            Step.ETAPA_7: Etapa7SubstituicaoE206(self.fge, self.sirep),
            Step.ETAPA_8: Etapa8PIGPesquisa(self.pig),
            Step.ETAPA_9: Etapa9PIGLancamento(self.pig),
            Step.ETAPA_10: Etapa10SituacaoPlano(self.fge, self.sirep),
            Step.ETAPA_11: Etapa11Rescisao(self.fge, self.sirep),
            Step.ETAPA_12: Etapa12Comunicacao(self.cns),
            Step.ETAPA_13: Etapa13Dossie(),
        }

    def run_steps(self, steps: List[Step]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for s in steps:
            out[s] = self.map[s].execute()
        return out
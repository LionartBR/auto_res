"""Stub implementations for adapters used during development and tests."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable

from sirep.infra.config import settings

from .base import CEFGDAdapter, CNSAdapter, FGEAdapter, PIGAdapter, SirepAdapter


class FGEStub(FGEAdapter):
    def listar_planos_presc_sem_974(self) -> Iterable[Dict[str, Any]]:
        yield {"numero_plano": "PLN001", "tipo": "MENSAL", "situacao": "P. RESC"}
        yield {"numero_plano": "PLN002", "tipo": "TRIMESTRAL", "situacao": "P. RESC"}

    def obter_saldo_total(self, numero_plano: str) -> float:
        return 12_345.67

    def plano_tem_grde(self, numero_plano: str) -> bool:
        return numero_plano.endswith("2")

    def listar_debitos_confessados(self, numero_plano: str) -> Iterable[Dict[str, Any]]:
        return [
            {"inscricao_tipo": "CNPJ", "inscricao": "00123456000199", "competencia": "2024-05"},
            {"inscricao_tipo": "CEI", "inscricao": "123456789012", "competencia": "2024-06"},
        ]

    def consultar_notificado(self, inscricao: str, competencia: str) -> bool:
        return competencia.endswith("05")

    def executar_rescisao(self, numero_plano: str) -> bool:
        return not settings.DRY_RUN


class SirepStub(SirepAdapter):
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def listar_sem_tratamento(self) -> list[Dict[str, Any]]:
        return [
            {"numero_plano": numero_plano, **dados}
            for numero_plano, dados in self._store.items()
            if dados.get("status") == "Sem Tratamento"
        ]

    def carga_complementar(self, linhas: list[Dict[str, Any]]) -> None:
        for linha in linhas:
            self._store[linha["CARTEIRA"]] = {
                "status": "Sem Tratamento",
                "dados": linha,
            }

    def atualizar_plano(self, numero_plano: str, campos: Dict[str, Any]) -> None:
        dados = self._store.setdefault(
            numero_plano,
            {
                "status": "Sem Tratamento",
                "dados": {},
            },
        )
        dados["dados"].update(campos)


class CEFGDStub(CEFGDAdapter):
    def plano_e_especial(self, numero_plano: str) -> bool:
        return numero_plano.endswith("1")


class CNSStub(CNSAdapter):
    def enviar_comunicacao(
        self, inscricoes: list[str], titulo: str, corpo: str
    ) -> Dict[str, str]:
        # Retorna NSU fake. DRY_RUN evita efeitos reais.
        return {inscricao: f"NSU-{inscricao[-6:]}" for inscricao in inscricoes}


class PIGStub(PIGAdapter):
    def pesquisar_guias(
        self,
        inscricao: str,
        competencia_ini: str,
        competencia_fim: str,
        data_ini: str,
    ) -> list[Dict[str, Any]]:
        return [
            {
                "inscricao": inscricao,
                "competencia": competencia_ini,
                "valor": 100.0,
                "tipo": "GRDE",
                "data_pagamento": str(datetime.utcnow().date()),
            }
        ]

    def lancar_guia(self, registro: Dict[str, Any]) -> bool:
        return not settings.DRY_RUN


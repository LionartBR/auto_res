from __future__ import annotations

from typing import Dict, Optional

GESTAO_STAGE_DEFINITIONS: Dict[int, str] = {
    1: "Etapa 1 – Captura de Plano",
    2: "Etapa 2 – Situação Especial",
    3: "Etapa 3 – Liquidação Anterior",
    4: "Etapa 4 – Guia GRDE",
}

GESTAO_STAGE_LABELS: Dict[int, str] = {
    numero: f"Gestão da Base – {descricao}"
    for numero, descricao in GESTAO_STAGE_DEFINITIONS.items()
}

_GESTAO_STAGE_ALIAS: Dict[str, int] = {
    "captura": 1,
    "captura de plano": 1,
    "situação especial": 2,
    "liquidação anterior": 3,
    "grde": 4,
    "guia grde": 4,
}

TRATAMENTO_STAGE_DEFINITIONS: Dict[int, str] = {
    1: "Etapa 1 – Aproveitamento de Recolhimentos",
    2: "Etapa 2 – Substituição – Confissão x Notificação Fiscal",
    3: "Etapa 3 – Pesquisa de Guias no SFG (PIG)",
    4: "Etapa 4 – Lançamento de Guias no FGE (PIG)",
    5: "Etapa 5 – Situação do Plano",
    6: "Etapa 6 – Rescisão",
    7: "Etapa 7 – Comunicação da Rescisão",
}

TRATAMENTO_STAGE_LABELS: Dict[int, str] = {
    numero: f"Tratamento – {descricao}"
    for numero, descricao in TRATAMENTO_STAGE_DEFINITIONS.items()
}


def infer_gestao_stage_numero(etapa: str | None, progresso: int | None = None) -> Optional[int]:
    """Retorna o número da etapa de gestão a partir do nome ou progresso."""

    if progresso and progresso > 0:
        if progresso in GESTAO_STAGE_DEFINITIONS:
            return progresso
    if etapa:
        chave = etapa.strip().lower()
        if chave in _GESTAO_STAGE_ALIAS:
            return _GESTAO_STAGE_ALIAS[chave]
    return None

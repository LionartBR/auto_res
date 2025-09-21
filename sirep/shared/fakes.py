from __future__ import annotations

import random
from datetime import date, timedelta
from typing import List

__all__ = [
    "TIPOS_PARCELAMENTO",
    "gerar_razao_social",
    "gerar_periodo",
    "gerar_cnpjs",
    "gerar_bases",
]

TIPOS_PARCELAMENTO = [
    "PARCELAMENTO ORDINÁRIO",
    "PARCELAMENTO ESPECIAL",
    "PARCELAMENTO SIMPLIFICADO",
]

_RAZAO_PREFIX = [
    "INDÚSTRIA",
    "COMÉRCIO",
    "SERVIÇOS",
    "TECNOLOGIA",
    "GRUPO",
    "CONSÓRCIO",
    "ALIMENTOS",
    "ENGENHARIA",
]

_RAZAO_MIDDLE = [
    "ALFA",
    "BETA",
    "ÔMEGA",
    "DELTA",
    "PRIME",
    "UNIÃO",
    "GERAL",
    "MASTER",
]

_RAZAO_SUFFIX = [
    "DO BRASIL",
    "GLOBAL",
    "NACIONAL",
    "LTDA",
    "S.A.",
    "ME",
    "EIRELI",
    "& CIA",
]

_UF_CODES = [
    "AC",
    "AL",
    "AM",
    "AP",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MG",
    "MS",
    "MT",
    "PA",
    "PB",
    "PE",
    "PI",
    "PR",
    "RJ",
    "RN",
    "RO",
    "RR",
    "RS",
    "SC",
    "SE",
    "SP",
    "TO",
    "BH",
    "BR",
]


def gerar_razao_social() -> str:
    prefix = random.choice(_RAZAO_PREFIX)
    middle = random.choice(_RAZAO_MIDDLE)
    suffix = random.choice(_RAZAO_SUFFIX)
    return f"{prefix} {middle} {suffix}"


def gerar_periodo() -> str:
    inicio = date.today() - timedelta(days=random.randint(365, 1500))
    fim = inicio + timedelta(days=random.randint(90, 720))
    return f"{inicio.strftime('%m/%Y')} a {fim.strftime('%m/%Y')}"


def gerar_cnpjs() -> List[str]:
    quantidade = random.randint(1, 3)
    valores: List[str] = []
    for _ in range(quantidade):
        numero = random.randint(0, 99999999999999)
        valores.append(_formatar_cnpj(numero))
    return valores


def gerar_bases() -> List[str]:
    quantidade = random.randint(1, 3)
    return random.sample(_UF_CODES, k=quantidade)


def _formatar_cnpj(valor: int) -> str:
    s = f"{valor:014d}"
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"

from __future__ import annotations

from typing import Dict, Any


def build_notepad_txt(notes: Dict[str, Any]) -> str:
    """Monta o TXT padronizado. Para campos não preenchidos, mantém linha vazia."""

    def g(key: str) -> str:
        value = notes.get(key, "") if notes else ""
        if value is None:
            return ""
        return str(value).strip()

    lines: list[str] = []
    add = lines.append

    add("DEPURAÇÃO PARCELAMENTO PASSÍVEL DE RESCISÃO")
    add("=================================================================================")
    add(f"PLANO: {g('PLANO')}")
    add(f"CNPJ/CEI: {g('CNPJ_CEI')}")
    add(f"RAZÃO SOCIAL: {g('RAZAO_SOCIAL')}")
    add("=================================================================================")
    add("E50H – PARCELAS EM ATRASO")
    add("Parcela Valor Parcela Atualizado Data Vencimento")
    atrasos = g("E50H_PARCELAS_ATRASO")
    if atrasos:
        add(atrasos)
    add("=================================================================================")
    add("E544 – DETALHES DO PARCELAMENTO")
    add(f"TIPO: {g('E544_TIPO')}")
    add(f"DATA DE SOLICITAÇÃO: {g('E544_DATA_SOLICITACAO')}")
    add(f"PERÍODO: {g('E544_PERIODO')}")
    cn = g("E544_CNPJS")
    add("CNPJ:")
    if cn:
        add(cn)
    add("=================================================================================")
    add("E398 – CONSULTA BASES MATRIZ E FILIAIS")
    bs = g("E398_BASES")
    inline_base = (bs if bs and "\n" not in bs else "").strip()
    add("BASES: " + inline_base)
    if bs and "\n" in bs:
        add(bs)
    add("=================================================================================")
    add("E555 – ANÁLISE DE OUTRO PLANO EM DIA")
    analise = g("E555_ANALISE_OUTRO_PLANO")
    if analise:
        add(analise)
    add("=================================================================================")
    add("E213 – APROVEITAMENTO DE RECOLHIMENTOS")
    aproveitamento = g("E213_APROVEITAMENTO_RECOLHIMENTOS")
    if aproveitamento:
        add(aproveitamento)
    add("=================================================================================")
    add("E206 – SUBSTITUIÇÃO – CONFISSÃO x NOTIFICAÇÃO FISCAL")
    substituicao = g("E206_SUBSTITUICAO_CONFISSAO_NOTIFICACAO")
    if substituicao:
        add(substituicao)
    add("=================================================================================")
    add("PESQUISA DE OCORRÊNCIAS 21")
    oc21 = g("OC21_RESULTADOS")
    oc21_exc = g("OC21_EXCLUSAO_GUIAS")
    if oc21:
        add(oc21)
        if oc21_exc:
            add(oc21_exc)
    oc21_table = g("OC21_TABELA")
    if oc21_table:
        add(oc21_table)
    add("=================================================================================")
    add("PESQUISA DE GUIAS NO SFG")
    pesquisa_guias = g("PESQUISA_GUIAS_SFG")
    if pesquisa_guias:
        add(pesquisa_guias)
    add("=================================================================================")
    add("LANÇAMENTO DE GUIAS NO FGE")
    lancamento_guias = g("LANCAMENTO_GUIAS_FGE")
    if lancamento_guias:
        add(lancamento_guias)
    add("=================================================================================")
    add("PESQUISA DE DUPLICIDADE")
    duplicidade = g("PESQUISA_DUPLICIDADE")
    if duplicidade:
        add(duplicidade)
    add("=================================================================================")
    add("E554 - RESCISÃO")
    add(f"DATA DA RESCISÃO NO FGE: {g('E554_DATA_RESCISAO_FGE')}")
    add(f"DATA DA COMUNICAÇÃO: {g('E554_DATA_COMUNICACAO')}")
    add(f"MÉTODO DE COMUNICAÇÃO (CNS/EMAIL): {g('E554_METODO_COMUNICACAO')}")
    add(f"NSU OU ENDEREÇO DE EMAIL: {g('E554_NSU_OU_EMAIL')}")
    add(f"NOME DO DOSSIÊ: {g('E554_NOME_DOSSIE')}")
    add(f"DATA DE FINALIZAÇÃO NO SIREP: {g('E554_DATA_FINALIZACAO_SIREP')}")
    add("=================================================================================")
    add("OUTRAS OBSERVAÇÕES (que julgar necessárias)")
    obs_txt = g("OUTRAS_OBSERVACOES").strip("\n")
    if obs_txt:
        add(obs_txt)

    return "\n".join(lines) + "\n"

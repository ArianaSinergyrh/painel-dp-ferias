"""
Carrega/salva as tabelas de INSS/IRRF (Parametros) no Supabase, em vez de
ficarem fixas no código — assim qualquer admin atualiza pela tela quando a
lei mudar, sem precisar mexer em nada técnico.

Os parâmetros são guardados por `tipo_processo` (hoje só 'ferias') para que,
quando outros processos de DP forem adicionados ao painel (ex.: rescisão),
cada um tenha sua própria tabela de parâmetros sem precisar mudar o schema.
"""
from __future__ import annotations

from core.calculo import Parametros
from core.auth import get_client

TIPO_PROCESSO_PADRAO = "ferias"


def carregar_parametros(tipo_processo: str = TIPO_PROCESSO_PADRAO) -> Parametros:
    sb = get_client()
    p = Parametros()

    faixas = (
        sb.table("parametros_faixas")
        .select("*")
        .eq("tipo_processo", tipo_processo)
        .eq("ativo", True)
        .order("faixa_ordem")
        .execute()
    ).data

    if faixas:
        inss = [
            (f["valor_ate"], float(f["aliquota"]), float(f["parcela_deduzir"]))
            for f in faixas if f["tabela"] == "INSS"
        ]
        irrf = [
            (f["valor_ate"], float(f["aliquota"]), float(f["parcela_deduzir"]))
            for f in faixas if f["tabela"] == "IRRF"
        ]
        if inss:
            p.inss = inss
        if irrf:
            p.irrf = irrf

    gerais = (
        sb.table("parametros_gerais")
        .select("*")
        .eq("tipo_processo", tipo_processo)
        .execute()
    ).data
    mapa = {g["chave"]: float(g["valor"]) for g in gerais}
    p.dep_deducao = mapa.get("dep_deducao", p.dep_deducao)
    p.ded_simplificada = mapa.get("ded_simplificada", p.ded_simplificada)
    p.redutor_limite = mapa.get("redutor_limite", p.redutor_limite)
    p.redutor_a = mapa.get("redutor_a", p.redutor_a)
    p.redutor_b = mapa.get("redutor_b", p.redutor_b)
    p.tolerancia = mapa.get("tolerancia", p.tolerancia)
    return p


def salvar_faixas(tabela: str, faixas: list, tipo_processo: str = TIPO_PROCESSO_PADRAO):
    """`faixas`: lista de dicts {faixa_ordem, valor_ate, aliquota, parcela_deduzir}."""
    sb = get_client()
    sb.table("parametros_faixas").update({"ativo": False}).eq("tipo_processo", tipo_processo).eq("tabela", tabela).execute()
    for f in faixas:
        sb.table("parametros_faixas").insert({
            "tipo_processo": tipo_processo,
            "tabela": tabela,
            "faixa_ordem": f["faixa_ordem"],
            "valor_ate": f["valor_ate"],
            "aliquota": f["aliquota"],
            "parcela_deduzir": f["parcela_deduzir"],
            "ativo": True,
        }).execute()


def salvar_geral(chave: str, valor: float, tipo_processo: str = TIPO_PROCESSO_PADRAO, descricao: str = ""):
    sb = get_client()
    sb.table("parametros_gerais").upsert({
        "chave": chave,
        "tipo_processo": tipo_processo,
        "valor": valor,
        "descricao": descricao,
    }, on_conflict="chave,tipo_processo").execute()

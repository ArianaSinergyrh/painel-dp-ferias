import pandas as pd
import streamlit as st

from core.auth import exigir_login, empresas_do_usuario, get_client, eh_admin

st.set_page_config(page_title="Histórico — Painel DP", page_icon="📜", layout="wide")
exigir_login()

st.title("📜 Histórico de processamentos")

sb = get_client()
empresas = empresas_do_usuario()
ids_empresas = [e["id"] for e in empresas]

query = sb.table("processamentos").select("*, empresas(nome), perfis(nome_completo)").order("criado_em", desc=True)
if not eh_admin():
    query = query.in_("empresa_id", ids_empresas or [-1])
registros = query.limit(200).execute().data

if not registros:
    st.info("Nenhum processamento registrado ainda.")
else:
    linhas = [{
        "Data": r["criado_em"],
        "Cliente": r["empresas"]["nome"] if r.get("empresas") else r["empresa_id"],
        "Analista": r["perfis"]["nome_completo"] if r.get("perfis") else r["usuario_id"],
        "Processo": r.get("tipo_processo", "ferias"),
        "Arquivo": r["nome_arquivo"],
        "Funcionários": r["total_funcionarios"],
        "OK": r["total_ok"],
        "Verificar": r["total_verificar"],
        "Sem dados": r["total_sem_dados"],
    } for r in registros]
    st.dataframe(pd.DataFrame(linhas), use_container_width=True, height=600)

import streamlit as st
import pandas as pd

from core.auth import exigir_login, eh_admin, get_client
from core.parametros_db import carregar_parametros, salvar_faixas, salvar_geral

st.set_page_config(page_title="Administração — Painel DP", page_icon="🛠️", layout="wide")
exigir_login()

if not eh_admin():
    st.error("Esta página é restrita a administradores.")
    st.stop()

st.title("🛠️ Administração")
sb = get_client()

aba_clientes, aba_acesso, aba_parametros = st.tabs(["Clientes", "Acesso dos analistas", "Parâmetros fiscais (Férias)"])

# ---------------------------------------------------------------- Clientes
with aba_clientes:
    st.subheader("Clientes (empresas atendidas)")
    empresas = sb.table("empresas").select("*").order("nome").execute().data
    st.dataframe(pd.DataFrame(empresas), use_container_width=True)

    with st.form("novo_cliente"):
        st.write("Cadastrar novo cliente")
        nome = st.text_input("Nome do cliente")
        cnpj = st.text_input("CNPJ (opcional)")
        enviar = st.form_submit_button("Cadastrar")
    if enviar and nome:
        sb.table("empresas").insert({"nome": nome, "cnpj": cnpj, "ativo": True}).execute()
        st.success(f"Cliente '{nome}' cadastrado.")
        st.rerun()

# ---------------------------------------------------------- Acesso analistas
with aba_acesso:
    st.subheader("Quais clientes cada analista pode ver")
    perfis = sb.table("perfis").select("*").execute().data
    empresas = sb.table("empresas").select("*").eq("ativo", True).order("nome").execute().data

    if not perfis or not empresas:
        st.info("Cadastre pelo menos um cliente e um analista (via convite no Supabase Auth) para liberar acessos.")
    else:
        mapa_perfil = {p.get("nome_completo") or p["id"]: p["id"] for p in perfis}
        mapa_empresa = {e["nome"]: e["id"] for e in empresas}

        with st.form("novo_acesso"):
            analista = st.selectbox("Analista", options=list(mapa_perfil.keys()))
            cliente = st.selectbox("Cliente", options=list(mapa_empresa.keys()))
            liberar = st.form_submit_button("Liberar acesso")
        if liberar:
            sb.table("acesso_empresas").upsert({
                "usuario_id": mapa_perfil[analista],
                "empresa_id": mapa_empresa[cliente],
            }).execute()
            st.success(f"Acesso liberado: {analista} → {cliente}")

        st.write("Acessos atuais:")
        acessos = (
            sb.table("acesso_empresas")
            .select("usuario_id, empresa_id, perfis(nome_completo), empresas(nome)")
            .execute()
            .data
        )
        linhas = [
            {"Analista": a["perfis"]["nome_completo"] if a.get("perfis") else a["usuario_id"],
             "Cliente": a["empresas"]["nome"] if a.get("empresas") else a["empresa_id"]}
            for a in acessos
        ]
        st.dataframe(pd.DataFrame(linhas), use_container_width=True)

    st.caption(
        "Novos analistas são criados direto no painel do Supabase (Authentication → Add user) "
        "com e-mail e senha provisória. Depois de criado, ele aparece aqui para você liberar os clientes."
    )

# --------------------------------------------------------- Parâmetros fiscais
with aba_parametros:
    st.subheader("Tabelas de INSS e IRRF usadas no recálculo de férias")
    st.caption("Atualize aqui quando a legislação mudar — não precisa mexer em código.")

    p = carregar_parametros()

    st.markdown("**Tabela INSS**")
    df_inss = pd.DataFrame(
        [{"faixa_ordem": i + 1, "valor_ate": ate, "aliquota": aliq, "parcela_deduzir": ded}
         for i, (ate, aliq, ded) in enumerate(p.inss)]
    )
    df_inss_edit = st.data_editor(df_inss, key="inss_editor", num_rows="dynamic", use_container_width=True)

    st.markdown("**Tabela IRRF**")
    df_irrf = pd.DataFrame(
        [{"faixa_ordem": i + 1, "valor_ate": ate, "aliquota": aliq, "parcela_deduzir": ded}
         for i, (ate, aliq, ded) in enumerate(p.irrf)]
    )
    df_irrf_edit = st.data_editor(df_irrf, key="irrf_editor", num_rows="dynamic", use_container_width=True)

    st.markdown("**Deduções e limites**")
    col1, col2, col3 = st.columns(3)
    dep_deducao = col1.number_input("Dedução por dependente (R$)", value=float(p.dep_deducao))
    ded_simplificada = col2.number_input("Dedução simplificada mensal (R$)", value=float(p.ded_simplificada))
    tolerancia = col3.number_input("Tolerância de diferença aceitável (R$)", value=float(p.tolerancia), step=0.01)
    col4, col5 = st.columns(2)
    redutor_limite = col4.number_input("Limite p/ redutor adicional (R$)", value=float(p.redutor_limite))
    redutor_a = col5.number_input("Constante A do redutor", value=float(p.redutor_a))
    redutor_b = st.number_input("Constante B do redutor", value=float(p.redutor_b), format="%.6f")

    if st.button("💾 Salvar parâmetros"):
        salvar_faixas("INSS", df_inss_edit.to_dict("records"))
        salvar_faixas("IRRF", df_irrf_edit.to_dict("records"))
        salvar_geral("dep_deducao", dep_deducao)
        salvar_geral("ded_simplificada", ded_simplificada)
        salvar_geral("tolerancia", tolerancia)
        salvar_geral("redutor_limite", redutor_limite)
        salvar_geral("redutor_a", redutor_a)
        salvar_geral("redutor_b", redutor_b)
        st.success("Parâmetros salvos. Já valem para o próximo processamento.")

import streamlit as st

from core.auth import exigir_login, empresas_do_usuario, get_client, eh_admin
from core.calculo import carregar_workbook, calcular_conferencia, resumo, gerar_excel_bytes, FormatoInvalido
from core.parametros_db import carregar_parametros
from core.auditoria import registrar, ACAO_CONFERENCIA, ACAO_HISTORICO

st.set_page_config(page_title="Férias — Painel DP", page_icon="🌴", layout="wide")
exigir_login()

st.title("🌴 Conferência de Férias")
st.caption(
    "Sobe o export mensal de Programação de Férias do sistema de folha "
    "(abas 'Todas', '644', 'FICHA' e, se existir, 'FÉRIAS CADASTRADAS DEPOIS') "
    "e recalcula o líquido de forma independente, comparando com o que o sistema já calculou."
)

empresas = empresas_do_usuario()
if not empresas:
    if eh_admin():
        st.warning(
            "Ainda não há nenhum cliente cadastrado. Vá em **🛠️ Administração → Clientes**, "
            "cadastre pelo menos um cliente e volte aqui — o campo de upload aparece logo abaixo "
            "da escolha do cliente."
        )
    else:
        st.warning(
            "Você não tem acesso a nenhum cliente ainda. Peça a um gerente ou diretor para "
            "liberar seu acesso em Administração → Acesso da equipe."
        )
    st.stop()

nomes_empresas = {e["nome"]: e["id"] for e in empresas}
empresa_nome = st.selectbox("Cliente", options=list(nomes_empresas.keys()))
empresa_id = nomes_empresas[empresa_nome]

arquivo = st.file_uploader("Arquivo mensal (.xlsx)", type=["xlsx"])

if arquivo is not None:
    try:
        wb = carregar_workbook(arquivo.getvalue())
    except FormatoInvalido as e:
        st.error(str(e))
        st.stop()

    parametros = carregar_parametros()
    with st.spinner("Recalculando..."):
        df = calcular_conferencia(wb, parametros)
    r = resumo(df)

    st.success(f"{r['total_funcionarios']} funcionários processados para {empresa_nome}.")

    # o log é automático: toda conferência processada fica registrada,
    # independente de a pessoa clicar em "registrar no histórico"
    chave_log = f"{empresa_id}|{arquivo.name}|{r['total_funcionarios']}"
    if st.session_state.get("_ultima_conferencia_logada") != chave_log:
        registrar(
            ACAO_CONFERENCIA,
            detalhe=(f"Arquivo '{arquivo.name}' — {r['total_funcionarios']} funcionários: "
                     f"{r['ok']} OK, {r['verificar']} a verificar, {r['sem_dados']} sem dados"),
            empresa_id=empresa_id, empresa_nome=empresa_nome,
        )
        st.session_state["_ultima_conferencia_logada"] = chave_log

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OK", r["ok"])
    c2.metric("A verificar", r["verificar"], delta_color="inverse")
    c3.metric("Sem dados no sistema", r["sem_dados"])
    c4.metric("Diferença total (R$)", f"{r['soma_liquido_sistema'] - r['soma_liquido_recalculado']:.2f}")

    def cor_status(row):
        cor = {
            "OK": "background-color: #DCFCE7",
            "VERIFICAR": "background-color: #FEE2E2",
            "SEM DADOS NO SISTEMA": "background-color: #FEF3C7",
        }.get(row["STATUS"], "")
        return [cor] * len(row)

    st.dataframe(df.style.apply(cor_status, axis=1), use_container_width=True, height=500)

    excel_bytes = gerar_excel_bytes(df)
    st.download_button(
        "⬇️ Baixar Excel da conferência",
        data=excel_bytes,
        file_name=f"Conferencia_Ferias_{empresa_nome.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if st.button("💾 Registrar este processamento no histórico"):
        sb = get_client()
        sb.table("processamentos").insert({
            "tipo_processo": "ferias",
            "empresa_id": empresa_id,
            "usuario_id": st.session_state["user_id"],
            "nome_arquivo": arquivo.name,
            "total_funcionarios": r["total_funcionarios"],
            "total_ok": r["ok"],
            "total_verificar": r["verificar"],
            "total_sem_dados": r["sem_dados"],
        }).execute()
        registrar(ACAO_HISTORICO, detalhe=f"Arquivo '{arquivo.name}'",
                  empresa_id=empresa_id, empresa_nome=empresa_nome)
        st.toast("Processamento registrado no histórico.")

    with st.expander("Como ler os status"):
        st.markdown(
            """
- **OK** — o líquido recalculado bate com o do sistema dentro da tolerância configurada.
- **VERIFICAR** — diferença acima da tolerância. Na maioria das vezes é **pensão alimentícia** não preenchida (o painel não tem como saber esse valor, ele não vem de nenhum export — é sempre manual).
- **SEM DADOS NO SISTEMA** — a matrícula só aparece em "cadastradas depois" e ainda não tem export de FICHA/644 correspondente. Reprocesse quando sair o export mais novo, ou confira manualmente.
"""
        )

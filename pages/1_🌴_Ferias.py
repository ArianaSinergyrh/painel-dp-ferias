"""
Conferência de Férias — recebe os arquivos CRUS do sistema Sinergy.

Não é preciso montar planilha nenhuma antes: sobe os três exports como eles
saem do sistema e o painel trata, cruza e monta o de-para.
"""
import streamlit as st

from core.auth import exigir_login, empresas_do_usuario, get_client, eh_admin, barra_lateral
from core.auditoria import registrar, ACAO_CONFERENCIA, ACAO_HISTORICO
from core.parametros_db import carregar_parametros
from core.preparacao import (FormatoInvalido, competencia_anterior, ler_ficha_ferias,
                             ler_programacao, ler_salarios)
from core.conferencia import gerar_excel, montar_conferencia, resumo

st.set_page_config(page_title="Férias — Painel DP", page_icon="🌴", layout="wide")
exigir_login()
barra_lateral()

st.title("🌴 Conferência de Férias")
st.caption(
    "Recalcula o líquido de férias de forma independente e compara com o que o sistema "
    "já calculou. As férias de um mês usam o salário do **mês anterior** — férias de "
    "setembro são calculadas sobre o salário de agosto."
)

empresas = empresas_do_usuario()
if empresas:
    nomes_empresas = {e["nome"]: e["id"] for e in empresas}
    empresa_nome = st.selectbox("Cliente", options=list(nomes_empresas.keys()))
    empresa_id = nomes_empresas[empresa_nome]
else:
    empresa_id, empresa_nome = None, "(sem cliente selecionado)"
    if eh_admin():
        st.info(
            "Ainda não há cliente cadastrado. Você pode conferir normalmente aqui embaixo — "
            "só o registro no histórico fica indisponível. Para cadastrar, vá em "
            "**🛠️ Administração → Clientes**."
        )
    else:
        st.info(
            "Você ainda não tem cliente liberado. Pode conferir normalmente aqui embaixo — "
            "só o registro no histórico fica indisponível."
        )

st.markdown("#### 📎 Anexe os três arquivos exportados do Sinergy")
st.caption("Pode subir os arquivos exatamente como saem do sistema, sem tratar nada antes.")

c1, c2, c3 = st.columns(3)
arq_prog = c1.file_uploader(
    "1. Programação de Férias", type=["xlsx"], key="up_prog",
    help="Relatório de Programação de Férias do mês que você está conferindo.")
arq_sal = c2.file_uploader(
    "2. Ficha do mês ANTERIOR (verba 644)", type=["xlsx"], key="up_sal",
    help="Consulta Ficha do mês anterior — é de onde sai o salário que baseia o cálculo.")
arq_fer = c3.file_uploader(
    "3. Ficha do mês das FÉRIAS", type=["xlsx"], key="up_fer",
    help="Consulta Ficha do mês das férias — é o cálculo que o sistema já fez.")

if not (arq_prog and arq_sal and arq_fer):
    st.stop()

try:
    with st.spinner("Lendo e tratando os arquivos..."):
        programacao = ler_programacao(arq_prog.getvalue())
        salarios, comp_salario = ler_salarios(arq_sal.getvalue())
        ficha, comp_ferias = ler_ficha_ferias(arq_fer.getvalue())
except FormatoInvalido as e:
    st.error(str(e))
    st.stop()
except Exception as e:
    st.error(f"Não consegui ler os arquivos: {e}")
    st.stop()

# confere se as competências fazem sentido entre si antes de calcular
esperado = competencia_anterior(comp_ferias)
if esperado and comp_salario and comp_salario != esperado:
    st.warning(
        f"As férias são da competência **{comp_ferias}**, então o salário deveria vir da ficha "
        f"de **{esperado}** — mas o arquivo enviado é de **{comp_salario}**. "
        "Confira se não trocou os arquivos 2 e 3 de lugar."
    )

parametros = carregar_parametros()
with st.spinner("Recalculando..."):
    df = montar_conferencia(programacao, salarios, ficha, parametros,
                            competencia_ferias=comp_ferias)
r = resumo(df)

st.success(
    f"{r['total_funcionarios']} funcionários conferidos — férias de {comp_ferias}, "
    f"salário base de {comp_salario}."
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("OK", r["ok"])
m2.metric("A verificar", r["verificar"], delta_color="inverse")
m3.metric("Outra competência / sem dados", r["sem_dados"])
m4.metric("Diferença total (R$)", f"{r['diferenca_total']:.2f}")

chave = f"{empresa_id}|{arq_fer.name}|{r['total_funcionarios']}"
if st.session_state.get("_ultima_conferencia_logada") != chave:
    registrar(
        ACAO_CONFERENCIA,
        detalhe=(f"Férias {comp_ferias} (salário {comp_salario}) — {r['total_funcionarios']} "
                 f"funcionários: {r['ok']} OK, {r['verificar']} a verificar, "
                 f"{r['sem_dados']} sem conferência neste mês"),
        empresa_id=empresa_id, empresa_nome=empresa_nome,
    )
    st.session_state["_ultima_conferencia_logada"] = chave

cores = {
    "OK": "background-color: #DCFCE7",
    "VERIFICAR": "background-color: #FEE2E2",
    "SEM SALÁRIO": "background-color: #FEF3C7",
    "SEM CÁLCULO NO SISTEMA": "background-color: #FEF3C7",
    "RECIBO EM OUTRA COMPETÊNCIA": "background-color: #E0E7FF",
}
st.dataframe(
    df.style.apply(lambda linha: [cores.get(linha["STATUS"], "")] * len(linha), axis=1),
    use_container_width=True, height=520,
)

st.download_button(
    "⬇️ Baixar o de-para em Excel",
    data=gerar_excel(df, comp_ferias, comp_salario),
    file_name=f"Conferencia_Ferias_{comp_ferias.replace('/', '-')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

divergentes = df[df["STATUS"] == "VERIFICAR"]
if not divergentes.empty:
    st.subheader("⚠️ O que precisa ser olhado")
    for _, x in divergentes.iterrows():
        with st.container(border=True):
            st.markdown(f"**{x['MAT']} — {x['NOME']}**  ·  diferença de R$ {x['DIFERENÇA']:,.2f}")
            st.caption(x["OBSERVAÇÃO"])

if empresa_id is None:
    st.caption("ℹ️ Sem cliente selecionado, este processamento não pode ser gravado no histórico.")
elif st.button("💾 Registrar este processamento no histórico"):
    get_client().table("processamentos").insert({
        "tipo_processo": "ferias",
        "empresa_id": empresa_id,
        "usuario_id": st.session_state["user_id"],
        "nome_arquivo": arq_fer.name,
        "total_funcionarios": r["total_funcionarios"],
        "total_ok": r["ok"],
        "total_verificar": r["verificar"],
        "total_sem_dados": r["sem_dados"],
    }).execute()
    registrar(ACAO_HISTORICO, detalhe=f"Férias {comp_ferias}",
              empresa_id=empresa_id, empresa_nome=empresa_nome)
    st.toast("Processamento registrado no histórico.")

with st.expander("Como ler os status"):
    st.markdown(
        """
- **OK** — o líquido recalculado bate com o do sistema dentro da tolerância configurada.
- **VERIFICAR** — diferença real, com o motivo provável descrito na coluna Observação.
- **RECIBO EM OUTRA COMPETÊNCIA** — a pessoa sai de férias neste mês, mas o pagamento
  (data de crédito) caiu no mês anterior, então o recibo dela está na ficha daquele mês.
  Não é divergência: é conferência que se faz junto com o outro mês.
- **SEM SALÁRIO** — não há verba 644 para a matrícula na ficha do mês anterior.
- **SEM CÁLCULO NO SISTEMA** — está na programação, mas o sistema ainda não calculou.

O **adiantamento de 13º** não é recalculado: ele depende dos avos já pagos no ano, que não
vêm nestes arquivos. O painel usa o valor do próprio sistema e avisa quando a programação
pede o adiantamento e a verba não aparece.
"""
    )

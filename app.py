"""
Painel DP — página inicial.

Arquitetura pensada para crescer: hoje só tem o processo de Férias, mas o
banco (tabela `processamentos`, `parametros_*` com coluna `tipo_processo`) e
a estrutura de páginas já foram feitos para receber novos processos de DP
(rescisão, folha mensal, benefícios, encargos, e-Social...) sem precisar
redesenhar login, cadastro de clientes ou controle de acesso — cada processo
novo vira só mais uma página em `pages/` + um módulo em `core/`.
"""
import streamlit as st

from core.auth import (
    exigir_login,
    eh_admin,
    empresas_do_usuario,
    sign_out,
    cargo_do_usuario,
    trocar_senha,
    recarregar_perfil,
    barra_lateral,
)
from core.auditoria import registrar, ACAO_LOGIN, ACAO_SENHA_PROPRIA

st.set_page_config(page_title="Painel DP — Sinergy", page_icon="🗂️", layout="wide")

exigir_login()

# registra a entrada uma única vez por sessão do navegador
if not st.session_state.get("_login_logado"):
    registrar(ACAO_LOGIN)
    st.session_state["_login_logado"] = True

barra_lateral()

st.title("🗂️ Painel DP — Automação de Processos")
st.caption("Escolha um processo no menu à esquerda para começar.")

empresas = empresas_do_usuario()
col1, col2, col3 = st.columns(3)
col1.metric("Clientes que você acessa", len(empresas))
col2.metric("Processos disponíveis hoje", 1)
col3.metric("Seu perfil", cargo_do_usuario().capitalize())

st.divider()
st.subheader("Processos")

st.markdown(
    """
- **🌴 Férias** — disponível. Confere o líquido de férias calculado pelo sistema contra um recálculo independente (INSS/IRRF), por cliente.
- **📄 Rescisão** — em breve.
- **💰 Folha mensal** — em breve.
- **🎁 Benefícios** — em breve.
- **🏛️ Encargos / eSocial** — em breve.
"""
)

st.subheader("Controle")
st.markdown(
    "- **📋 Log de Atividades** — quem fez o quê e quando: entradas no painel, conferências "
    "rodadas, clientes cadastrados, acessos liberados, mudanças de cargo e de parâmetros "
    "fiscais. Analista vê o próprio; coordenador e gerente veem a equipe; diretor vê tudo."
)

if not empresas:
    st.warning(
        "Você ainda não tem acesso a nenhum cliente. Peça para um administrador liberar na página de Administração."
    )

st.info("Use o menu à esquerda (📂 pages) para abrir o processo de **Férias**.")

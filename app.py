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
)

st.set_page_config(page_title="Painel DP — Sinergy", page_icon="🗂️", layout="wide")

exigir_login()

with st.sidebar:
    st.write(f"👤 {st.session_state.get('user_email', '')}")
    with st.expander("🔑 Trocar minha senha"):
        with st.form("trocar_senha_form"):
            nova = st.text_input("Nova senha", type="password")
            confirma = st.text_input("Confirme a nova senha", type="password")
            trocar = st.form_submit_button("Salvar nova senha")
        if trocar:
            if not nova or nova != confirma:
                st.error("As senhas precisam ser preenchidas e iguais.")
            elif len(nova) < 6:
                st.error("A senha precisa ter pelo menos 6 caracteres.")
            else:
                try:
                    trocar_senha(nova)
                    st.success("Senha alterada.")
                except Exception as e:
                    st.error(f"Não consegui trocar: {e}")
    if st.button("🔄 Recarregar meu perfil"):
        try:
            recarregar_perfil()
            st.toast("Perfil atualizado.")
            st.rerun()
        except Exception as e:
            st.error(f"Não consegui recarregar: {e}")
    if st.button("Sair"):
        sign_out()
        st.rerun()

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

if not empresas:
    st.warning(
        "Você ainda não tem acesso a nenhum cliente. Peça para um administrador liberar na página de Administração."
    )

st.info("Use o menu à esquerda (📂 pages) para abrir o processo de **Férias**.")

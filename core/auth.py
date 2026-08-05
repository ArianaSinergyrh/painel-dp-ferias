"""
Autenticação via Supabase Auth (login/senha) + carregamento do perfil do
analista (é admin? quais empresas/clientes pode ver?).

Mantém tudo em st.session_state para sobreviver aos reruns do Streamlit
dentro da mesma aba do navegador. Ao fechar/atualizar a aba, o analista
precisa logar de novo (comportamento aceitável para a v1 — dá pra evoluir
para um cookie persistente depois, se fizer falta).
"""
from __future__ import annotations

import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def sign_in(email: str, password: str):
    sb = get_client()
    resp = sb.auth.sign_in_with_password({"email": email, "password": password})
    if resp.user is None:
        raise RuntimeError("Login ou senha inválidos.")
    st.session_state["access_token"] = resp.session.access_token
    st.session_state["refresh_token"] = resp.session.refresh_token
    st.session_state["user_id"] = resp.user.id
    st.session_state["user_email"] = resp.user.email
    _load_perfil(resp.user.id)


def sign_out():
    sb = get_client()
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    for k in ["access_token", "refresh_token", "user_id", "user_email", "perfil", "empresas_acessiveis"]:
        st.session_state.pop(k, None)


def _load_perfil(user_id: str):
    sb = get_client()
    perfil = sb.table("perfis").select("*").eq("id", user_id).single().execute()
    st.session_state["perfil"] = perfil.data if perfil.data else {"is_admin": False, "nome_completo": ""}

    is_admin = st.session_state["perfil"].get("is_admin", False)
    if is_admin:
        empresas = sb.table("empresas").select("*").eq("ativo", True).order("nome").execute()
    else:
        acesso = (
            sb.table("acesso_empresas")
            .select("empresa_id, empresas(id, nome, cnpj)")
            .eq("usuario_id", user_id)
            .execute()
        )
        empresas_data = [row["empresas"] for row in acesso.data if row.get("empresas")]
        empresas = type("R", (), {"data": empresas_data})()
    st.session_state["empresas_acessiveis"] = empresas.data


def esta_logado() -> bool:
    return "user_id" in st.session_state


def eh_admin() -> bool:
    return bool(st.session_state.get("perfil", {}).get("is_admin", False))


def empresas_do_usuario() -> list:
    return st.session_state.get("empresas_acessiveis", [])


def exigir_login():
    """Chame no topo de cada página. Mostra o formulário de login e para a
    execução da página se o analista ainda não estiver autenticado."""
    if esta_logado():
        return

    st.title("🔐 Painel DP — Login")
    st.caption("Acesso restrito aos analistas cadastrados.")
    with st.form("login_form"):
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar")
    if entrar:
        try:
            sign_in(email, senha)
            st.rerun()
        except Exception as e:
            st.error(f"Não consegui autenticar: {e}")
    st.stop()

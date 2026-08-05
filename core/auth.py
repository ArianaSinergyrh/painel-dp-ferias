"""
Autenticação via Supabase Auth (login/senha) + carregamento do perfil do
usuário (cargo, quem ele supervisiona, quais empresas/clientes pode ver).

Hierarquia de cargos (definida em perfis.cargo):
    analista    -> só os clientes liberados diretamente para ele
    coordenador -> os dele + os dos analistas ligados a ele (supervisor_id)
    gerente     -> os dele + toda a equipe abaixo (times inteiros)
    diretor     -> todos os clientes, de todas as equipes

Mantém tudo em st.session_state para sobreviver aos reruns do Streamlit
dentro da mesma aba do navegador. Ao fechar/atualizar a aba, o usuário
precisa logar de novo (comportamento aceitável para a v1 — dá pra evoluir
para um cookie persistente depois, se fizer falta).
"""
from __future__ import annotations

import streamlit as st
from supabase import create_client, Client

CARGOS = ["analista", "coordenador", "gerente", "diretor"]
CARGOS_GESTAO = ("gerente", "diretor")  # quem tem acesso à página de Administração


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


def sign_up(email: str, password: str, nome_completo: str):
    """Autocadastro: qualquer pessoa pode criar sua própria conta. Ela entra
    como 'analista' sem nenhum cliente liberado — um gerente/diretor depois
    ajusta o cargo, o supervisor e libera os clientes na Administração."""
    sb = get_client()
    resp = sb.auth.sign_up({
        "email": email,
        "password": password,
        "options": {"data": {"nome_completo": nome_completo}},
    })
    if resp.user is None:
        raise RuntimeError("Não foi possível criar a conta.")
    return resp


def trocar_senha(nova_senha: str):
    """O próprio usuário logado troca a senha a qualquer momento."""
    sb = get_client()
    sb.auth.set_session(st.session_state["access_token"], st.session_state["refresh_token"])
    sb.auth.update_user({"password": nova_senha})


def enviar_reset_senha(email: str):
    """Gerente/diretor dispara um e-mail de redefinição de senha para
    qualquer usuário cadastrado."""
    sb = get_client()
    sb.auth.reset_password_for_email(email)


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
    dados = perfil.data if perfil.data else {"cargo": "analista", "is_admin": False, "nome_completo": ""}
    st.session_state["perfil"] = dados

    cargo = dados.get("cargo", "analista")
    if cargo == "diretor":
        empresas = sb.table("empresas").select("*").eq("ativo", True).order("nome").execute()
        empresas_data = empresas.data
    else:
        # eu + todo mundo abaixo de mim na hierarquia (vazio para analista comum,
        # que só enxerga a si mesmo)
        subordinados = sb.rpc("subordinados_de", {"usuario": user_id}).execute()
        ids = [row["id"] for row in subordinados.data] if subordinados.data else [user_id]
        acesso = (
            sb.table("acesso_empresas")
            .select("empresa_id, empresas(id, nome, cnpj)")
            .in_("usuario_id", ids)
            .execute()
        )
        vistos = {}
        for row in acesso.data:
            e = row.get("empresas")
            if e:
                vistos[e["id"]] = e
        empresas_data = list(vistos.values())
    st.session_state["empresas_acessiveis"] = empresas_data


def esta_logado() -> bool:
    return "user_id" in st.session_state


def cargo_do_usuario() -> str:
    return st.session_state.get("perfil", {}).get("cargo", "analista")


def eh_admin() -> bool:
    """Quem gerencia clientes, equipe e parâmetros fiscais (gerente/diretor)."""
    return cargo_do_usuario() in CARGOS_GESTAO


def empresas_do_usuario() -> list:
    return st.session_state.get("empresas_acessiveis", [])


def exigir_login():
    """Chame no topo de cada página. Mostra login/cadastro e para a
    execução da página se o usuário ainda não estiver autenticado."""
    if esta_logado():
        return

    st.title("🔐 Painel DP — Login")
    st.caption("Acesso restrito à equipe cadastrada.")

    aba_login, aba_cadastro = st.tabs(["Entrar", "Criar conta"])

    with aba_login:
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

    with aba_cadastro:
        st.caption(
            "Crie sua conta com seu e-mail e uma senha de sua escolha. "
            "Depois disso, peça a um gerente ou diretor para definir seu cargo, "
            "seu supervisor e liberar os clientes que você vai atender."
        )
        with st.form("cadastro_form"):
            nome = st.text_input("Nome completo")
            email_novo = st.text_input("E-mail", key="email_cadastro")
            senha_nova = st.text_input("Crie uma senha", type="password", key="senha_cadastro")
            senha_confirma = st.text_input("Confirme a senha", type="password", key="senha_cadastro_2")
            criar = st.form_submit_button("Criar conta")
        if criar:
            if not nome or not email_novo or not senha_nova:
                st.error("Preencha nome, e-mail e senha.")
            elif senha_nova != senha_confirma:
                st.error("As senhas não são iguais.")
            elif len(senha_nova) < 6:
                st.error("A senha precisa ter pelo menos 6 caracteres.")
            else:
                try:
                    sign_up(email_novo, senha_nova, nome)
                    st.success(
                        "Conta criada! Se pedirmos confirmação de e-mail, confira sua caixa de "
                        "entrada. Depois é só voltar na aba 'Entrar' e fazer login."
                    )
                except Exception as e:
                    st.error(f"Não consegui criar a conta: {e}")

    st.stop()

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

import time

import streamlit as st
from supabase import create_client, Client

try:
    import extra_streamlit_components as stx
    _TEM_COOKIE = True
except Exception:      # se a biblioteca faltar, o painel segue funcionando
    _TEM_COOKIE = False

CARGOS = ["analista", "coordenador", "gerente", "diretor"]

# Nível de cada cargo. Serve para responder "posso mexer no cargo desta pessoa?"
# — a regra é que ninguém concede um cargo acima do seu nem altera o cargo de
# quem está acima. Precisa bater com a função nivel_cargo() do banco.
NIVEL_CARGO = {"analista": 0, "coordenador": 1, "gerente": 2, "diretor": 3}

# Cadastro de clientes e tabelas de INSS/IRRF: só gerente e diretor, porque um
# erro ali afeta o cálculo de todos os clientes.
CARGOS_GESTAO = ("gerente", "diretor")

# Cargos e acessos da equipe, e ajuste das tabelas de INSS/IRRF: coordenador
# para cima. (Cadastro de cliente segue em CARGOS_GESTAO.)
CARGOS_EQUIPE = ("coordenador", "gerente", "diretor")

# Nome do cookie que mantém a pessoa logada depois de um F5.
COOKIE_SESSAO = "painel_dp_sessao"


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def _gerenciador_cookies():
    """O CookieManager desenha um componente na tela, então não pode ficar dentro
    de função cacheada — o Streamlit recusa widget em @st.cache_resource.
    Guardamos a instância no session_state, que sobrevive aos reruns."""
    if not _TEM_COOKIE:
        return None
    if "_cookie_mgr" not in st.session_state:
        st.session_state["_cookie_mgr"] = stx.CookieManager(key="painel_dp_cookie_mgr")
    return st.session_state["_cookie_mgr"]


def _guardar_sessao(refresh_token: str):
    """Grava o refresh token num cookie para a pessoa continuar logada após um
    F5. Guardamos só o refresh token (não a senha, não o token de acesso)."""
    if not _TEM_COOKIE:
        return
    try:
        from datetime import datetime, timedelta
        _gerenciador_cookies().set(
            COOKIE_SESSAO, refresh_token,
            expires_at=datetime.now() + timedelta(days=7),
            key="set_sessao",
        )
    except Exception:
        pass


def _limpar_cookie_sessao():
    if not _TEM_COOKIE:
        return
    try:
        _gerenciador_cookies().delete(COOKIE_SESSAO, key="del_sessao")
    except Exception:
        pass


def _restaurar_sessao() -> bool:
    """Tenta reabrir a sessão a partir do cookie. Retorna True se conseguiu.
    É o que faz o F5 (ou reabrir a aba) não cair de volta na tela de senha.

    Detalhe importante: o CookieManager é um componente de front-end. Na PRIMEIRA
    execução do script ele ainda não devolveu os cookies do navegador — retorna
    vazio. Só num ciclo seguinte o valor chega. Por isso aqui a gente dá algumas
    chances antes de desistir; sem isso o painel concluía "não tem cookie" cedo
    demais e mostrava a tela de senha mesmo com a sessão salva."""
    if not _TEM_COOKIE or st.session_state.get("_sessao_restaurada_falhou"):
        return False

    try:
        mgr = _gerenciador_cookies()
        cookies = mgr.get_all()
    except Exception:
        st.session_state["_sessao_restaurada_falhou"] = True
        return False

    token = (cookies or {}).get(COOKIE_SESSAO)

    if not token:
        tentativas = st.session_state.get("_tentativas_cookie", 0)
        if tentativas < 4:
            # o componente ainda não respondeu — espera um instante e tenta de novo
            st.session_state["_tentativas_cookie"] = tentativas + 1
            with st.spinner("Retomando sua sessão..."):
                time.sleep(0.45)
            st.rerun()
        st.session_state["_sessao_restaurada_falhou"] = True
        return False

    try:
        sb = get_client()
        resp = sb.auth.refresh_session(token)
        if not resp or not resp.user or not resp.session:
            raise RuntimeError("sessão expirada")
        perfil, empresas = _buscar_perfil(resp.user.id)
    except Exception:
        _limpar_cookie_sessao()
        st.session_state["_sessao_restaurada_falhou"] = True
        return False

    st.session_state["access_token"] = resp.session.access_token
    st.session_state["refresh_token"] = resp.session.refresh_token
    st.session_state["user_id"] = resp.user.id
    st.session_state["user_email"] = resp.user.email
    st.session_state["perfil"] = perfil
    st.session_state["empresas_acessiveis"] = empresas
    _guardar_sessao(resp.session.refresh_token)
    return True


def sign_in(email: str, password: str):
    """Autentica e só marca a sessão como logada DEPOIS que o perfil (cargo e
    clientes) foi carregado com sucesso.

    Isso é importante: se o carregamento do perfil falhar no meio do caminho,
    a sessão não pode ficar "meio logada" — antes isso acontecia e o painel
    seguia funcionando com o perfil vazio, caindo no padrão 'analista' mesmo
    para quem é diretor no banco. Agora, se algo falhar, o login falha de
    forma visível e a sessão é limpa."""
    sb = get_client()
    resp = sb.auth.sign_in_with_password({"email": email, "password": password})
    if resp.user is None:
        raise RuntimeError("Login ou senha inválidos.")

    try:
        perfil, empresas = _buscar_perfil(resp.user.id)
    except Exception:
        # não deixa resquício de sessão pela metade
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        raise

    st.session_state["access_token"] = resp.session.access_token
    st.session_state["refresh_token"] = resp.session.refresh_token
    st.session_state["user_id"] = resp.user.id
    st.session_state["user_email"] = resp.user.email
    st.session_state["perfil"] = perfil
    st.session_state["empresas_acessiveis"] = empresas
    _guardar_sessao(resp.session.refresh_token)


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
    for k in ["access_token", "refresh_token", "user_id", "user_email", "perfil",
              "empresas_acessiveis", "_login_logado",
              "_tentativas_cookie", "_sessao_restaurada_falhou"]:
        st.session_state.pop(k, None)
    _limpar_cookie_sessao()


def _buscar_perfil(user_id: str):
    """Lê o perfil (cargo, nome) e a lista de clientes que o usuário enxerga.
    Devolve (perfil, empresas). Levanta exceção se não conseguir ler o perfil —
    é melhor falhar de forma visível do que assumir 'analista' silenciosamente."""
    sb = get_client()
    perfil = sb.table("perfis").select("*").eq("id", user_id).single().execute()
    dados = perfil.data
    if not dados:
        raise RuntimeError(
            "Seu usuário está autenticado, mas não encontrei o perfil correspondente "
            "na tabela 'perfis'. Peça para um diretor verificar o cadastro."
        )
    if not dados.get("cargo"):
        raise RuntimeError(
            "Seu perfil não tem cargo definido. Peça para um gerente ou diretor "
            "ajustar o cargo na página de Administração."
        )

    cargo = dados["cargo"]
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
    return dados, empresas_data


def recarregar_perfil():
    """Relê cargo e clientes do banco sem precisar sair e entrar de novo.
    Útil logo depois que um diretor muda o cargo de alguém."""
    perfil, empresas = _buscar_perfil(st.session_state["user_id"])
    st.session_state["perfil"] = perfil
    st.session_state["empresas_acessiveis"] = empresas


def esta_logado() -> bool:
    return "user_id" in st.session_state


def cargo_do_usuario() -> str:
    return st.session_state.get("perfil", {}).get("cargo", "analista")


def eh_admin() -> bool:
    """Quem cadastra clientes e mexe nas tabelas fiscais (gerente/diretor)."""
    return cargo_do_usuario() in CARGOS_GESTAO


def gere_equipe() -> bool:
    """Quem define cargos e libera acessos da equipe (coordenador para cima)."""
    return cargo_do_usuario() in CARGOS_EQUIPE


def pode_editar_parametros() -> bool:
    """Quem ajusta as tabelas de INSS/IRRF (coordenador para cima)."""
    return cargo_do_usuario() in CARGOS_EQUIPE


def meu_nivel() -> int:
    return NIVEL_CARGO.get(cargo_do_usuario(), 0)


def cargos_que_posso_conceder() -> list:
    """Ninguém concede um cargo acima do seu."""
    return [c for c in CARGOS if NIVEL_CARGO[c] <= meu_nivel()]


def posso_alterar_cargo_de(perfil: dict) -> tuple:
    """Diz se dá para mexer no cargo desta pessoa e, se não der, por quê.
    Retorna (pode, motivo).

    O diretor pode mexer no próprio cargo — é o topo da hierarquia e responde
    pela empresa. Coordenador e gerente não podem, porque se rebaixassem a si
    mesmos perderiam o acesso e ficariam dependendo de outra pessoa."""
    sou_eu = perfil.get("id") == st.session_state.get("user_id")
    if not gere_equipe():
        return False, "Seu cargo não permite alterar cargos."
    if sou_eu and cargo_do_usuario() != "diretor":
        return False, "Você não altera o seu próprio cargo — peça a um diretor."
    if NIVEL_CARGO.get(perfil.get("cargo", "analista"), 0) > meu_nivel():
        return False, "Esta pessoa tem cargo acima do seu."
    return True, ""


def empresas_do_usuario() -> list:
    return st.session_state.get("empresas_acessiveis", [])


def exigir_login():
    """Chame no topo de cada página. Mostra login/cadastro e para a
    execução da página se o usuário ainda não estiver autenticado."""
    if esta_logado():
        return
    if _restaurar_sessao():
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


def barra_lateral():
    """Barra lateral padrão de todas as páginas: quem está logado, trocar senha,
    recarregar perfil e sair. Antes o botão Sair só existia na página inicial —
    quem estivesse em Férias ou no Log não tinha como sair sem voltar."""
    from core.auditoria import registrar, ACAO_SENHA_PROPRIA

    with st.sidebar:
        st.write(f"👤 {st.session_state.get('user_email', '')}")
        st.caption(f"Perfil: **{cargo_do_usuario().capitalize()}**")

        with st.expander("🔑 Trocar minha senha"):
            with st.form("trocar_senha_form_lateral"):
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
                        registrar(ACAO_SENHA_PROPRIA)
                        st.success("Senha alterada.")
                    except Exception as e:
                        st.error(f"Não consegui trocar: {e}")

        if st.button("🔄 Recarregar meu perfil", key="btn_recarregar_lateral"):
            try:
                recarregar_perfil()
                st.toast("Perfil atualizado.")
                st.rerun()
            except Exception as e:
                st.error(f"Não consegui recarregar: {e}")

        if st.button("🚪 Sair", key="btn_sair_lateral", type="primary"):
            sign_out()
            st.rerun()

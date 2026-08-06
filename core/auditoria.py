"""
Log de atividades — registra o que cada pessoa da equipe faz no painel.

Regras de projeto:
  * O log NUNCA pode quebrar o fluxo do usuário. Se a gravação falhar (rede,
    permissão, tabela ainda não criada), a ação principal segue normalmente e
    o erro é engolido de propósito.
  * Guardamos nome, e-mail, cargo e nome do cliente no momento da ação — e não
    só os ids — para o log continuar legível mesmo que o cadastro mude depois.
  * A gravação em nome de outra pessoa é bloqueada pelo próprio banco (RLS),
    então não dá para forjar um registro.

Quem lê o quê é decidido pelo banco: analista vê só o dele; coordenador e
gerente veem a equipe abaixo; diretor vê tudo.
"""
from __future__ import annotations

import streamlit as st

from core.auth import get_client

# ------------------------------------------------------------------ ações
# Nomes fixos para o filtro da tela de Log ficar consistente.
ACAO_LOGIN = "Entrou no painel"
ACAO_CONFERENCIA = "Conferência de férias"
ACAO_DOWNLOAD = "Baixou Excel da conferência"
ACAO_HISTORICO = "Registrou no histórico"
ACAO_CLIENTE_NOVO = "Cadastrou cliente"
ACAO_ACESSO_LIBERADO = "Liberou acesso a cliente"
ACAO_CARGO_ALTERADO = "Alterou cargo/supervisor"
ACAO_PARAMETROS = "Alterou parâmetros fiscais"
ACAO_RESET_SENHA = "Enviou redefinição de senha"
ACAO_SENHA_PROPRIA = "Trocou a própria senha"

ACOES = [
    ACAO_LOGIN,
    ACAO_CONFERENCIA,
    ACAO_DOWNLOAD,
    ACAO_HISTORICO,
    ACAO_CLIENTE_NOVO,
    ACAO_ACESSO_LIBERADO,
    ACAO_CARGO_ALTERADO,
    ACAO_PARAMETROS,
    ACAO_RESET_SENHA,
    ACAO_SENHA_PROPRIA,
]


def registrar(acao: str, detalhe: str = "", empresa_id=None, empresa_nome: str = ""):
    """Grava uma linha no log. Silencioso por design — ver docstring do módulo."""
    try:
        perfil = st.session_state.get("perfil") or {}
        usuario_id = st.session_state.get("user_id")
        if not usuario_id:
            return
        get_client().table("log_atividades").insert({
            "usuario_id": usuario_id,
            "usuario_nome": perfil.get("nome_completo") or "",
            "usuario_email": st.session_state.get("user_email") or perfil.get("email") or "",
            "cargo": perfil.get("cargo") or "",
            "acao": acao,
            "detalhe": (detalhe or "")[:1000],
            "empresa_id": empresa_id,
            "empresa_nome": empresa_nome or "",
        }).execute()
    except Exception:
        pass


def buscar(limite: int = 1000):
    """Lê o log que o usuário logado tem permissão de ver (o filtro é do banco)."""
    resp = (
        get_client()
        .table("log_atividades")
        .select("*")
        .order("criado_em", desc=True)
        .limit(limite)
        .execute()
    )
    return resp.data or []

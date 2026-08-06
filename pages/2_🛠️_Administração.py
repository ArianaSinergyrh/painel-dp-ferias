import streamlit as st
import pandas as pd

from core.auth import (exigir_login, eh_admin, get_client, CARGOS, CARGOS_GESTAO,
                       enviar_reset_senha, recarregar_perfil)
from core.parametros_db import carregar_parametros, salvar_faixas, salvar_geral
from core.auditoria import (registrar, ACAO_CLIENTE_NOVO, ACAO_ACESSO_LIBERADO,
                            ACAO_CARGO_ALTERADO, ACAO_PARAMETROS, ACAO_RESET_SENHA)

st.set_page_config(page_title="Administração — Painel DP", page_icon="🛠️", layout="wide")
exigir_login()

if not eh_admin():
    st.error("Esta página é restrita a gerentes e diretores.")
    st.stop()

st.title("🛠️ Administração")
sb = get_client()

aba_equipe, aba_clientes, aba_acesso, aba_parametros = st.tabs(
    ["Equipe (cargos e hierarquia)", "Clientes", "Acesso da equipe", "Parâmetros fiscais (Férias)"]
)

# -------------------------------------------------------------------- Equipe
with aba_equipe:
    st.subheader("Cargos e hierarquia")
    st.caption(
        "Cada pessoa cria a própria conta na tela de login (aba 'Criar conta'). "
        "Aqui você define o cargo dela e quem é o supervisor direto — isso decide "
        "automaticamente quais clientes ela enxerga: um coordenador/gerente vê os "
        "clientes liberados para ele **e** para todo mundo abaixo dele na hierarquia; "
        "o diretor vê todos os clientes, de todas as equipes."
    )
    perfis_todos = sb.table("perfis").select("*").order("nome_completo").execute().data

    if not perfis_todos:
        st.info("Ainda não há ninguém cadastrado. Peça para a pessoa criar a conta na tela de login.")
    else:
        mapa_nome = {p["id"]: (p.get("nome_completo") or p["id"]) for p in perfis_todos}
        for p in perfis_todos:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 1, 2, 1])
                col1.write(f"**{p.get('nome_completo') or '(sem nome)'}**")
                cargo_atual = p.get("cargo", "analista")
                novo_cargo = col2.selectbox(
                    "Cargo", options=CARGOS, index=CARGOS.index(cargo_atual) if cargo_atual in CARGOS else 0,
                    key=f"cargo_{p['id']}", label_visibility="collapsed",
                )
                opcoes_supervisor = {"— sem supervisor —": None}
                opcoes_supervisor.update({nome: pid for pid, nome in mapa_nome.items() if pid != p["id"]})
                supervisor_atual = p.get("supervisor_id")
                nome_supervisor_atual = mapa_nome.get(supervisor_atual, "— sem supervisor —") if supervisor_atual else "— sem supervisor —"
                opcoes_lista = list(opcoes_supervisor.keys())
                novo_supervisor_nome = col3.selectbox(
                    "Supervisor", options=opcoes_lista,
                    index=opcoes_lista.index(nome_supervisor_atual) if nome_supervisor_atual in opcoes_lista else 0,
                    key=f"sup_{p['id']}", label_visibility="collapsed",
                )
                sou_eu = p["id"] == st.session_state.get("user_id")
                if sou_eu and novo_cargo not in CARGOS_GESTAO:
                    col4.caption("⚠️ Você não pode rebaixar o seu próprio cargo.")

                if col4.button("Salvar", key=f"salvar_{p['id']}"):
                    # Trava de segurança: se a pessoa se rebaixasse para analista ou
                    # coordenador, perderia na hora o acesso a esta página e ficaria
                    # sem como voltar — só com SQL direto no banco.
                    total_diretores = sum(1 for x in perfis_todos if x.get("cargo") == "diretor")
                    if sou_eu and novo_cargo not in CARGOS_GESTAO:
                        st.error(
                            f"Não dá para mudar o seu próprio cargo para '{novo_cargo}': você perderia "
                            "o acesso a esta página e ficaria travada para fora. Peça a outro gerente "
                            "ou diretor para fazer essa alteração."
                        )
                    elif (sou_eu and cargo_atual == "diretor" and novo_cargo != "diretor"
                          and total_diretores <= 1):
                        st.error(
                            "Você é a única pessoa com cargo de diretor. Promova outra a diretor antes "
                            "de mudar o seu próprio cargo, senão a empresa fica sem ninguém com acesso "
                            "a todos os clientes."
                        )
                    else:
                        sb.table("perfis").update({
                            "cargo": novo_cargo,
                            "supervisor_id": opcoes_supervisor[novo_supervisor_nome],
                        }).eq("id", p["id"]).execute()
                        registrar(ACAO_CARGO_ALTERADO,
                                  detalhe=(f"{p.get('nome_completo') or p['id']}: cargo '{cargo_atual}' → "
                                           f"'{novo_cargo}'; supervisor → {novo_supervisor_nome}"))
                        if sou_eu:
                            # atualiza a própria sessão na hora, sem precisar sair e entrar
                            try:
                                recarregar_perfil()
                            except Exception:
                                pass
                        st.success("Atualizado.")
                        st.rerun()
                email_pessoa = p.get("email")
                if email_pessoa:
                    if st.button(f"✉️ Enviar redefinição de senha ({email_pessoa})", key=f"reset_{p['id']}"):
                        try:
                            enviar_reset_senha(email_pessoa)
                            registrar(ACAO_RESET_SENHA, detalhe=f"Para {email_pessoa}")
                            st.toast(f"E-mail de redefinição enviado para {email_pessoa}.")
                        except Exception as e:
                            st.error(f"Não consegui enviar: {e}")
                else:
                    col4.caption("Sem e-mail registrado ainda.")

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
        registrar(ACAO_CLIENTE_NOVO, detalhe=f"Cliente '{nome}'" + (f" (CNPJ {cnpj})" if cnpj else ""),
                  empresa_nome=nome)
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
            registrar(ACAO_ACESSO_LIBERADO, detalhe=f"{analista} passou a acessar '{cliente}'",
                      empresa_id=mapa_empresa[cliente], empresa_nome=cliente)
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
        "Cada pessoa cria a própria conta na tela de login. Depois disso ela aparece aqui "
        "para você liberar os clientes — e na aba 'Equipe' para definir cargo e supervisor."
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
        registrar(ACAO_PARAMETROS,
                  detalhe=(f"INSS {len(df_inss_edit)} faixas, IRRF {len(df_irrf_edit)} faixas; "
                           f"dependente R$ {dep_deducao}, simplificada R$ {ded_simplificada}, "
                           f"tolerância R$ {tolerancia}"))
        st.success("Parâmetros salvos. Já valem para o próximo processamento.")

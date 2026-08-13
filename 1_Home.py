from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from app_core.auth import is_admin, is_authenticated, user_email, user_name
from app_core.ui import apply_branding, configure_page, render_card, render_hero, render_logo, render_sidebar
from auth_functions import get_user_role
from mongo_config import auth_client
import user_management_db as umdb

log = logging.getLogger("financeiro_verdio.home")

configure_page("Financeiro Verdio", layout="wide", icon="💳")
branding = apply_branding()


if not is_authenticated():
    st.markdown(
        "<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'] {display:none !important;}</style>",
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([1, 1.15, 1])
    with center:
        render_logo(max_width=300, branding=branding)
        st.markdown(f"## {branding['system_name']}")
        st.caption(branding["system_subtitle"])

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("E-mail", placeholder="nome@empresa.com")
            password = st.text_input("Senha", type="password", placeholder="Sua senha")
            submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if submitted:
            normalized_email = email.strip().lower()
            if not normalized_email or not password:
                st.warning("Preencha e-mail e senha.")
            else:
                try:
                    user = auth_client.sign_in_with_email_and_password(normalized_email, password)
                    uid = str(user.get("localId") or "")
                    st.session_state["user_info"] = user
                    st.session_state["role"] = get_user_role(uid)
                    st.session_state["name"] = normalized_email.split("@")[0].replace(".", " ").title()
                    umdb.log_action("INFO", normalized_email, "Login realizado.")
                    st.rerun()
                except Exception:
                    log.warning("Falha de login para %s", normalized_email, exc_info=True)
                    st.error("E-mail ou senha inválidos.")

    st.stop()

# Mantém a role sincronizada com o MongoDB durante a navegação.
try:
    uid = str(st.session_state.get("user_info", {}).get("localId") or "")
    if uid:
        st.session_state["role"] = get_user_role(uid)
except Exception:
    pass

render_sidebar()
render_hero(
    branding["system_name"],
    f"Bem-vindo, {user_name()}. Acompanhe os principais fluxos financeiros e acesse as rotinas pelo menu lateral.",
)

summary_cols = st.columns(4)
with summary_cols[0]:
    render_card("Sessão", user_name(), user_email())
with summary_cols[1]:
    render_card("Perfil", "Administrador" if is_admin() else "Usuário", "Permissões aplicadas em todas as páginas")
with summary_cols[2]:
    render_card("Ambiente", "Online", "MongoDB e autenticação inicializados")
with summary_cols[3]:
    render_card("Identidade", "Personalizável", "Logo, sidebar e cores gerenciadas pelo administrador")

st.markdown("### Acessos rápidos")
quick = st.columns(4)
with quick[0]:
    render_card("Faturamento", "Verdio", "Processamento completo, conferência e exportação")
    st.page_link("pages/5_Faturamento_Verdio_Completo.py", label="Abrir faturamento")
with quick[1]:
    render_card("Faturamento", "Parceiros", "Apuração de filiais e parceiros")
    st.page_link("pages/6_Faturamento_Parceiros.py", label="Abrir parceiros")
with quick[2]:
    render_card("Consolidado", "Resumo mensal", "Visão resumida por período")
    st.page_link("pages/6_Resumo_Faturamento_Mensal.py", label="Abrir resumo")
with quick[3]:
    render_card("Histórico", "Faturamentos", "Auditoria dos registros já gerados")
    st.page_link("pages/7_Historico_Faturamento.py", label="Abrir histórico")

if is_admin():
    st.markdown("### Gestão administrativa")
    admin_cols = st.columns(4)
    with admin_cols[0]:
        render_card("Comercial", "Contratos", "Prazos e tabelas específicas por cliente")
        st.page_link("pages/7_Contratos_Clientes.py", label="Gerenciar contratos")
    with admin_cols[1]:
        render_card("Operação", "Estoque e preços", "Inventário e três faixas de preço")
        st.page_link("pages/94_Gestao_Estoque.py", label="Gerenciar estoque")
    with admin_cols[2]:
        render_card("Segurança", "Usuários", "Acessos, perfis e bloqueios")
        st.page_link("pages/2_Gerenciar_Usuarios.py", label="Gerenciar usuários")
    with admin_cols[3]:
        render_card("Aparência", "Identidade visual", "Logos, cores e apresentação da plataforma")
        st.page_link("pages/90_Identidade_Visual.py", label="Personalizar sistema")

recent = umdb.get_recent_billing(limit=6)
if recent:
    st.markdown("### Faturamentos recentes")
    frame = pd.DataFrame(recent)
    display_columns = [
        column
        for column in ["cliente", "periodo_relatorio", "valor_total", "data_geracao", "gerado_por"]
        if column in frame.columns
    ]
    if display_columns:
        st.dataframe(
            frame[display_columns],
            use_container_width=True,
            hide_index=True,
            column_config={
                "cliente": "Cliente",
                "periodo_relatorio": "Período",
                "valor_total": st.column_config.NumberColumn("Valor total", format="R$ %.2f"),
                "data_geracao": st.column_config.DatetimeColumn("Gerado em", format="DD/MM/YYYY HH:mm"),
                "gerado_por": "Gerado por",
            },
        )

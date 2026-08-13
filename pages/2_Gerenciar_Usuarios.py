from __future__ import annotations

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import streamlit as st

from app_core.auth import (
    require_auth,
    user_email,
    user_username,
)
from app_core.shared_identity import connection_diagnostics
from app_core.ui import (
    apply_branding,
    render_hero,
    render_sidebar,
)
from auth_functions import get_all_users, update_finance_access
import user_management_db as umdb

st.set_page_config(
    page_title="Acessos ao Financeiro",
    page_icon="👥",
    layout="wide",
)
apply_branding()
require_auth(admin=True)
render_sidebar()
render_hero(
    "Acessos ao Financeiro",
    "Os usuários, senhas e status globais vêm do Simulador de Telemetria. "
    "Nesta tela você controla apenas quem pode acessar o Financeiro e com qual perfil.",
)

diagnostics = connection_diagnostics()
if not diagnostics.get("ok"):
    st.error("Não foi possível acessar simulador_db.users.")
    st.write(diagnostics)
    st.stop()

users = get_all_users()
current_username = user_username()
current_email = user_email()

enabled_count = sum(1 for item in users if item.get("finance_enabled"))
admin_count = sum(
    1
    for item in users
    if item.get("finance_enabled")
    and str(item.get("finance_role", "")).lower() == "admin"
)
global_active_count = sum(1 for item in users if item.get("global_active"))

metric_cols = st.columns(4)
metric_cols[0].metric("Identidades compartilhadas", len(users))
metric_cols[1].metric("Usuários globais ativos", global_active_count)
metric_cols[2].metric("Com acesso ao Financeiro", enabled_count)
metric_cols[3].metric("Admins do Financeiro", admin_count)

st.info(
    "Cadastro, senha, nome, e-mail, bloqueio global e exclusão continuam sendo "
    "administrados no Simulador de Telemetria. Alterações feitas lá são refletidas "
    "automaticamente aqui."
)

if not users:
    st.warning(
        "Nenhum usuário foi encontrado em simulador_db.users. "
        "Cadastre o primeiro usuário no Simulador."
    )
    st.stop()

table_rows = []
for item in users:
    table_rows.append(
        {
            "Usuário": item.get("username", ""),
            "Nome": item.get("name", ""),
            "E-mail": item.get("email", ""),
            "Perfil no Simulador": item.get("global_role", "user"),
            "Conta global": "Ativa" if item.get("global_active") else "Inativa",
            "Acesso Financeiro": "Sim" if item.get("finance_enabled") else "Não",
            "Perfil Financeiro": item.get("finance_role", "Usuário"),
            "Último acesso Financeiro": item.get("last_finance_sign_in_at"),
        }
    )

st.dataframe(
    pd.DataFrame(table_rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Último acesso Financeiro": st.column_config.DatetimeColumn(
            "Último acesso Financeiro",
            format="DD/MM/YYYY HH:mm",
        ),
    },
)

st.markdown("### Editar autorização")

users_by_username = {
    str(item.get("username") or ""): item
    for item in users
    if item.get("username")
}
selected_username = st.selectbox(
    "Usuário",
    list(users_by_username),
    format_func=lambda username: (
        f"{users_by_username[username].get('name', username)} "
        f"({username})"
    ),
)
selected = users_by_username[selected_username]

global_active = bool(selected.get("global_active"))
if not global_active:
    st.warning(
        "Esta conta está inativa no Simulador. Mesmo que a autorização financeira "
        "esteja marcada, ela não poderá entrar até ser reativada no Simulador."
    )

role_options = ["Usuário", "Admin"]
current_finance_role = str(selected.get("finance_role") or "Usuário")
if current_finance_role not in role_options:
    current_finance_role = "Usuário"

with st.form("finance_access_form"):
    col_access, col_role = st.columns(2)
    with col_access:
        enabled = st.toggle(
            "Permitir acesso ao Financeiro",
            value=bool(selected.get("finance_enabled")),
            disabled=not global_active,
        )
    with col_role:
        role = st.selectbox(
            "Perfil no Financeiro",
            role_options,
            index=role_options.index(current_finance_role),
        )

    st.caption(
        "A senha não é armazenada no Financeiro. O login valida diretamente "
        "o hashed_password existente em simulador_db.users."
    )
    save = st.form_submit_button(
        "Salvar autorização",
        type="primary",
        use_container_width=True,
    )

if save:
    if selected_username == current_username and not enabled:
        st.error("Você não pode remover o próprio acesso durante a sessão.")
    elif update_finance_access(
        selected_username,
        enabled=enabled,
        role=role,
    ):
        umdb.log_action(
            "WARNING",
            current_email or current_username,
            "Autorização financeira de usuário alterada.",
            {
                "username": selected_username,
                "finance_enabled": enabled,
                "finance_role": role,
            },
        )
        st.success("Autorização atualizada.")
        st.rerun()

st.markdown("---")
st.caption(
    "Fonte de identidade: simulador_db.users · Dados financeiros: financeiro_verdio.*"
)

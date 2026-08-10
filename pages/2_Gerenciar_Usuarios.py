from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import streamlit as st

from app_core.auth import require_auth, user_email
from app_core.ui import apply_branding, render_hero, render_sidebar
from auth_functions import create_new_user, get_all_users, update_user_role, update_user_status
import user_management_db as umdb

st.set_page_config(page_title="Gestão de usuários", page_icon="👥", layout="wide")
apply_branding()
require_auth(admin=True)
render_sidebar()
render_hero(
    "Gestão de usuários",
    "Administre acessos, perfis e status das contas do Financeiro Verdio.",
)

users = get_all_users()
current_email = user_email()

active_count = sum(1 for item in users if not item.get("disabled"))
admin_count = sum(1 for item in users if str(item.get("role", "")).lower() == "admin")
metric_cols = st.columns(3)
metric_cols[0].metric("Usuários cadastrados", len(users))
metric_cols[1].metric("Contas ativas", active_count)
metric_cols[2].metric("Administradores", admin_count)

create_tab, manage_tab = st.tabs(["Novo usuário", "Usuários cadastrados"])

with create_tab:
    with st.form("new_user_form", clear_on_submit=True):
        st.markdown("#### Criar acesso")
        email = st.text_input("E-mail do novo usuário", placeholder="nome@empresa.com")
        password = st.text_input("Senha inicial", type="password", help="Use pelo menos 8 caracteres.")
        role = st.selectbox("Nível de acesso", ["Usuário", "Admin"])
        create = st.form_submit_button("Criar usuário", type="primary", use_container_width=True)

    if create:
        if create_new_user(email, password, role):
            umdb.log_action(
                "INFO",
                current_email,
                "Usuário criado pelo administrador.",
                {"email": email.strip().lower(), "role": role},
            )
            st.success("Usuário criado com sucesso.")
            st.rerun()

with manage_tab:
    if not users:
        st.info("Nenhum usuário encontrado.")
    else:
        table_rows = []
        for item in users:
            created_ms = item.get("created_at")
            sign_in_ms = item.get("last_sign_in_at")
            created = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc) if created_ms else None
            last_sign_in = datetime.fromtimestamp(sign_in_ms / 1000, tz=timezone.utc) if sign_in_ms else None
            table_rows.append(
                {
                    "E-mail": item.get("email", ""),
                    "Perfil": item.get("role", "Usuário"),
                    "Status": "Inativo" if item.get("disabled") else "Ativo",
                    "Criado em": created,
                    "Último acesso": last_sign_in,
                }
            )

        st.dataframe(
            pd.DataFrame(table_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Criado em": st.column_config.DatetimeColumn("Criado em", format="DD/MM/YYYY HH:mm"),
                "Último acesso": st.column_config.DatetimeColumn("Último acesso", format="DD/MM/YYYY HH:mm"),
            },
        )

        users_by_email = {str(item.get("email") or ""): item for item in users}
        selected_email = st.selectbox("Selecionar usuário para editar", list(users_by_email))
        selected = users_by_email[selected_email]

        with st.form("edit_user_form"):
            col_role, col_status = st.columns(2)
            current_role = selected.get("role", "Usuário")
            role_options = ["Usuário", "Admin"]
            new_role = col_role.selectbox(
                "Perfil",
                role_options,
                index=role_options.index(current_role) if current_role in role_options else 0,
            )
            active = col_status.toggle("Acesso ativo", value=not bool(selected.get("disabled")))
            save = st.form_submit_button("Salvar alterações", type="primary", use_container_width=True)

        if save:
            if selected_email.strip().lower() == current_email and not active:
                st.error("Você não pode desabilitar a própria conta durante a sessão.")
            else:
                changed = False
                if new_role != selected.get("role"):
                    changed = update_user_role(selected["uid"], new_role) or changed
                desired_disabled = not active
                if desired_disabled != bool(selected.get("disabled")):
                    changed = update_user_status(selected["uid"], desired_disabled) or changed

                if changed:
                    umdb.log_action(
                        "WARNING",
                        current_email,
                        "Acesso de usuário alterado.",
                        {
                            "email": selected_email,
                            "role": new_role,
                            "active": active,
                        },
                    )
                    st.success("Usuário atualizado.")
                    st.rerun()
                else:
                    st.info("Nenhuma alteração foi necessária.")

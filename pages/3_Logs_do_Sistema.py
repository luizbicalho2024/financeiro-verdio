# pages/3_Logs_do_Sistema.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Logs do Sistema", page_icon="📋")

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO (CORRIGIDO) ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("🚫 Você não tem permissão para acessar esta página. Apenas Administradores.")
    st.stop()

# --- BARRA LATERAL PADRONIZADA ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")

# --- Conteúdo da Página (sem alterações) ---
st.title("📋 Logs do Sistema")
st.markdown("Registro de todas as ações importantes realizadas na plataforma.")
st.markdown("---")

logs = umdb.get_system_logs()

if not logs:
    st.info("Nenhum log encontrado.")
else:
    df_logs = pd.DataFrame(logs)
    st.sidebar.header("Filtrar Logs")
    levels = df_logs['level'].unique()
    selected_levels = st.sidebar.multiselect("Nível do Log", options=levels, default=list(levels))
    users = df_logs['user'].unique()
    selected_users = st.sidebar.multiselect("Usuário", options=users, default=list(users))
    
    filtered_df = df_logs[
        df_logs['level'].isin(selected_levels) &
        df_logs['user'].isin(selected_users)
    ]
    
    if filtered_df.empty:
        st.warning("Nenhum log corresponde aos filtros selecionados.")
    else:
        st.dataframe(
            filtered_df,
            column_config={
                "timestamp": st.column_config.DatetimeColumn("Data e Hora", format="DD/MM/YYYY HH:mm:ss"),
                "level": "Nível",
                "user": "Usuário",
                "message": "Mensagem",
                "details": "Detalhes"
            },
            use_container_width=True,
            hide_index=True
        )

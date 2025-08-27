import streamlit as st
import pandas as pd
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Logs do Sistema", page_icon="📋")

# --- VERIFICAÇÃO DE AUTENTICAÇÃO E NÍVEL DE ACESSO ---
if not st.session_state.get("authentication_status"):
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role") != "admin":
    st.error("🚫 Você não tem permissão para acessar esta página. Apenas Administradores.")
    st.stop()

st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")

st.title("📋 Logs do Sistema")
st.markdown("Registro de todas as ações importantes realizadas na plataforma.")
st.markdown("---")

logs = umdb.get_system_logs()

if not logs:
    st.info("Nenhum log encontrado.")
else:
    df_logs = pd.DataFrame(logs)
    
    # --- FILTROS ---
    st.sidebar.header("Filtrar Logs")
    
    # Filtro por nível de log
    levels = df_logs['level'].unique()
    selected_levels = st.sidebar.multiselect("Nível do Log", options=levels, default=levels)
    
    # Filtro por usuário
    users = df_logs['user'].unique()
    selected_users = st.sidebar.multiselect("Usuário", options=users, default=users)
    
    # Aplicar filtros
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

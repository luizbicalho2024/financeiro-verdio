# pages/99_Logs_do_Sistema.py
import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
# Adicione 'pytz' ao seu arquivo requirements.txt se ainda não estiver lá
import pytz

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Logs do Sistema", page_icon="📋")

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
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

# --- FUNÇÕES AUXILIARES ---
@st.cache_data(ttl=300)
def carregar_logs():
    """Busca e cacheia os logs do sistema."""
    return umdb.get_system_logs()

def to_csv(df):
    """Converte DataFrame para CSV para download."""
    return df.to_csv(index=False).encode('utf-8')

# --- INICIALIZAÇÃO E CARREGAMENTO DE DADOS ---
st.title("📋 Logs do Sistema")
st.markdown("Registro detalhado de todas as ações importantes realizadas na plataforma.")

if st.sidebar.button("🔄 Atualizar Logs"):
    st.cache_data.clear()

logs_data = carregar_logs()

if not logs_data:
    st.info("Nenhum log encontrado no sistema.")
    st.stop()

df_logs = pd.DataFrame(logs_data)
# Converte a coluna de timestamp para datetime com fuso horário correto (America/Manaus para RO)
try:
    ro_timezone = pytz.timezone('America/Manaus')
    df_logs['timestamp'] = pd.to_datetime(df_logs['timestamp']).dt.tz_convert(ro_timezone)
except Exception:
    # Fallback caso a conversão de fuso falhe
    df_logs['timestamp'] = pd.to_datetime(df_logs['timestamp'])


# --- BARRA LATERAL DE FILTROS ---
st.sidebar.header("Filtrar Logs")

# 1. Filtro por Data
today = datetime.now(ro_timezone).date()
start_date = st.sidebar.date_input("Data de Início", today - timedelta(days=7))
end_date = st.sidebar.date_input("Data de Fim", today)

# 2. Filtro por Texto na Mensagem
search_term = st.sidebar.text_input("Buscar na Mensagem:")

# 3. Filtros por Nível e Usuário
levels = sorted(df_logs['level'].unique())
selected_levels = st.sidebar.multiselect("Nível do Log", options=levels, default=list(levels))

users = sorted(df_logs['user'].unique())
selected_users = st.sidebar.multiselect("Usuário", options=users, default=list(users))

# --- LÓGICA DE FILTRAGEM ---
filtered_df = df_logs[
    (df_logs['timestamp'].dt.date >= start_date) &
    (df_logs['timestamp'].dt.date <= end_date) &
    (df_logs['level'].isin(selected_levels)) &
    (df_logs['user'].isin(selected_users))
]

if search_term:
    filtered_df = filtered_df[filtered_df['message'].str.contains(search_term, case=False, na=False)]

st.markdown("---")

# --- PAINEL DE RESUMO (DASHBOARD) ---
st.subheader("Análise Rápida do Período")

if not filtered_df.empty:
    col1, col2, col3 = st.columns(3)
    
    # Total de logs no período
    col1.metric("Total de Logs Filtrados", len(filtered_df))

    # Erros nas últimas 24h
    twenty_four_hours_ago = datetime.now(ro_timezone) - timedelta(hours=24)
    errors_last_24h = df_logs[
        (df_logs['level'] == 'ERROR') & 
        (df_logs['timestamp'] > twenty_four_hours_ago)
    ].shape[0]
    col2.metric("Erros (últimas 24h)", errors_last_24h)
    
    # Usuário mais ativo
    most_active_user = filtered_df['user'].mode()[0] if not filtered_df['user'].empty else "N/A"
    col3.metric("Usuário Mais Ativo", most_active_user)
    
    # Gráfico de logs por nível
    st.markdown("##### Distribuição de Logs por Nível")
    log_level_counts = filtered_df['level'].value_counts()
    st.bar_chart(log_level_counts)

else:
    st.info("Nenhum log encontrado para os filtros selecionados.")
    st.stop()

st.markdown("---")

# --- PAGINAÇÃO ---
st.subheader("Registros Detalhados")
if 'log_page' not in st.session_state:
    st.session_state.log_page = 0

ITEMS_PER_PAGE = 25
start_idx = st.session_state.log_page * ITEMS_PER_PAGE
end_idx = start_idx + ITEMS_PER_PAGE
total_pages = (len(filtered_df) - 1) // ITEMS_PER_PAGE + 1

paginated_df = filtered_df.iloc[start_idx:end_idx]

col_a, col_b, col_c = st.columns([1, 3, 1])

if col_a.button("⬅️ Página Anterior", disabled=(st.session_state.log_page == 0)):
    st.session_state.log_page -= 1
    st.rerun()

col_b.markdown(f"<p style='text-align: center;'>Página {st.session_state.log_page + 1} de {total_pages}</p>", unsafe_allow_html=True)

if col_c.button("Próxima Página ➡️", disabled=(st.session_state.log_page >= total_pages - 1)):
    st.session_state.log_page += 1
    st.rerun()


# --- EXIBIÇÃO DOS LOGS COM DETALHES EXPANSÍVEIS ---
if paginated_df.empty and len(filtered_df) > 0:
    st.warning("Página inválida. Retornando para a primeira página.")
    st.session_state.log_page = 0
    st.rerun()

for index, row in paginated_df.iterrows():
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        st.markdown(f"**Data e Hora:**\n{row['timestamp'].strftime('%d/%m/%Y %H:%M:%S')}")
    with col2:
        st.markdown(f"**Usuário:** `{row['user']}`")
        # Aplica cor baseada no nível do log
        if row['level'] == 'ERROR':
            st.error(f"**Mensagem:** {row['message']}")
        elif row['level'] == 'WARNING':
            st.warning(f"**Mensagem:** {row['message']}")
        else:
            st.info(f"**Mensagem:** {row['message']}")
    with col3:
        # Botão para expandir detalhes
        if isinstance(row.get('details'), dict) and row.get('details'):
             with st.expander("Ver Detalhes"):
                st.json(row['details'])
        else:
            st.caption("Sem detalhes")

# --- AÇÃO DE DOWNLOAD ---
st.sidebar.markdown("---")
st.sidebar.download_button(
    label="📥 Baixar Logs Filtrados (CSV)",
    data=to_csv(filtered_df),
    file_name=f"logs_{start_date}_a_{end_date}.csv",
    mime="text/csv",
)

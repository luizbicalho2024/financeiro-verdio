# pages/7_Historico_Faturamento.py
import streamlit as st
import pandas as pd
import user_management_db as umdb

st.set_page_config(
    layout="wide",
    page_title="Histórico de Faturamento",
    page_icon="🧾"
)

if not st.session_state.get("authentication_status"):
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.title("🧾 Histórico de Faturamento")
st.markdown("Análise dos relatórios de faturamento gerados e salvos na plataforma.")

history_data = umdb.get_billing_history()

if not history_data:
    st.info("Nenhum histórico de faturamento encontrado.")
    st.stop()

df = pd.DataFrame(history_data)
# Converte o timestamp do Firebase para datetime
df['data_geracao'] = pd.to_datetime(df['data_geracao'])
df['mes_ano'] = df['data_geracao'].dt.to_period('M').astype(str)

st.subheader("Evolução do Faturamento Total por Mês")
faturamento_mensal = df.groupby('mes_ano')['valor_total'].sum().sort_index()
if not faturamento_mensal.empty:
    st.bar_chart(faturamento_mensal)

with st.expander("Ver todos os registros de faturamento", expanded=True):
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "_id": None, # Esconde a coluna de ID
            "data_geracao": st.column_config.DatetimeColumn("Data de Geração", format="DD/MM/YYYY HH:mm"),
            "cliente": "Cliente",
            "periodo_relatorio": "Período do Relatório",
            "valor_total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f"),
            "terminais_cheio": "Nº Fat. Cheio",
            "terminais_proporcional": "Nº Fat. Proporcional",
            "gerado_por": "Gerado Por"
        }
    )

# --- Seção de Exclusão para Admins ---
if st.session_state.get("role") == "Admin":
    st.markdown("---")
    st.subheader("🗑️ Gerenciar Histórico")
    
    options_map = {
        f"{row['cliente']} - {row['data_geracao'].strftime('%d/%m/%Y %H:%M')} (R$ {row['valor_total']:.2f})": row['_id']
        for index, row in df.iterrows()
    }
    
    selected_option = st.selectbox(
        "Selecione o registro que deseja excluir:",
        options=options_map.keys(),
        index=None,
        placeholder="Escolha um registro para excluir..."
    )

    if selected_option:
        history_id_to_delete = options_map[selected_option]
        st.warning(f"**Atenção:** Você está prestes a excluir o registro '{selected_option}'. Esta ação é irreversível.")
        
        if st.button("Confirmar Exclusão", type="primary"):
            if umdb.delete_billing_history(history_id_to_delete):
                st.rerun()

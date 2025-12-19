import sys
import os
import pandas as pd
import streamlit as st
import altair as alt

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb
import auth_functions as af

st.set_page_config(layout="wide", page_title="Histórico", page_icon="📜")

if "user_info" not in st.session_state:
    st.error("🔒 Login necessário.")
    st.stop()

af.render_sidebar()
st.title("📜 Histórico Financeiro")

history = umdb.get_billing_history()
if not history:
    st.info("Sem dados históricos.")
    st.stop()

df = pd.DataFrame(history)

# Tratamento
if 'data_geracao' in df.columns:
    df['data_geracao'] = pd.to_datetime(df['data_geracao']).dt.tz_localize(None)
    df['Data'] = df['data_geracao'].dt.strftime('%d/%m/%Y %H:%M')

# --- GRÁFICO ---
st.subheader("Evolução")
chart_data = df.groupby('periodo_relatorio')['valor_total'].sum().reset_index()
c = alt.Chart(chart_data).mark_bar().encode(
    x=alt.X('periodo_relatorio', title='Mês'),
    y=alt.Y('valor_total', title='Faturamento (R$)'),
    tooltip=['periodo_relatorio', 'valor_total']
).properties(height=250)
st.altair_chart(c, use_container_width=True)

st.divider()

# --- TABELA INTERATIVA ---
c1, c2 = st.columns([2, 1])
with c1:
    st.subheader("Registros")
    df_show = df[['cliente', 'periodo_relatorio', 'valor_total', 'Data', '_id']].rename(columns={
        'cliente': 'Cliente', 'periodo_relatorio': 'Mês', 'valor_total': 'Total'
    })
    
    evt = st.dataframe(
        df_show, 
        column_config={"Total": st.column_config.NumberColumn(format="R$ %.2f")},
        column_order=['Cliente', 'Mês', 'Total', 'Data'],
        hide_index=True,
        use_container_width=True,
        selection_mode="single-row",
        on_select="rerun"
    )

sel = evt.selection.get("rows", [])
sel_data = None
if sel:
    sid = df_show.iloc[sel[0]]['_id']
    sel_data = next((h for h in history if h["_id"] == sid), None)

with c2:
    st.subheader("Detalhes")
    if sel_data:
        st.info(f"{sel_data['cliente']}")
        st.write(f"Ref: {sel_data['periodo_relatorio']}")
        st.write(f"Total: R$ {sel_data['valor_total']:,.2f}")
        
        itens = sel_data.get('itens_detalhados', [])
        if itens:
            df_i = pd.DataFrame(itens)
            st.dataframe(
                df_i[['Terminal', 'Valor a Faturar']], 
                column_config={"Valor a Faturar": st.column_config.NumberColumn(format="R$ %.2f")},
                hide_index=True, 
                use_container_width=True, 
                height=300
            )
        else:
            st.caption("Sem itens detalhados salvos.")
            
        if st.button("🗑️ Excluir Registro", type="primary"):
            if umdb.delete_billing_history(sel_data['_id']):
                st.rerun()
    else:
        st.caption("Selecione um registro ao lado.")

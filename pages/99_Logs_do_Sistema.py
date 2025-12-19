import sys
import os
import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb
import auth_functions as af

st.set_page_config(layout="wide", page_title="Auditoria", page_icon="🛡️")
if "user_info" not in st.session_state: st.stop()

af.render_sidebar()
st.title("🛡️ Auditoria do Sistema")

logs = umdb.get_system_logs()
if not logs: st.info("Sem logs."); st.stop()

df = pd.DataFrame(logs)
if 'timestamp' in df.columns:
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)

c1, c2 = st.columns(2)
user_f = c1.text_input("Filtrar Usuário")
lvl_f = c2.multiselect("Nível", ["INFO", "WARNING", "ERROR"], ["INFO", "WARNING", "ERROR"])

df_show = df.copy()
if user_f: df_show = df_show[df_show['user'].str.contains(user_f, case=False)]
if lvl_f: df_show = df_show[df_show['level'].isin(lvl_f)]

for _, row in df_show.iterrows():
    c = "blue"
    if row['level'] == 'WARNING': c = "orange"
    if row['level'] == 'ERROR': c = "red"
    
    with st.expander(f":{c}[{row['level']}] - {row['timestamp']} - {row['message']}"):
        st.write(f"Usuário: {row['user']}")
        if row.get('details'): st.json(row['details'])

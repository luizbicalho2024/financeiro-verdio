# pages/2_Gerenciar_Usuarios.py
import streamlit as st
import pandas as pd
# A importação agora vai funcionar pois o arquivo auth_functions.py existe na raiz
from auth_functions import initialize_firebase, get_all_users, create_new_user, update_user_status, update_user_role

# --- INICIALIZAÇÃO E VERIFICAÇÃO DE PERMISSÃO ---
st.set_page_config(page_title="Gerenciar Usuários", layout="wide")
db = initialize_firebase()

# Verifica se o usuário está logado e se é Admin
if not st.session_state.get('logged_in') or st.session_state.get('user_role') != 'Admin':
    st.error("Acesso negado. Você precisa ser um administrador para ver esta página.")
    st.stop()

# --- PÁGINA DE GERENCIAMENTO ---
st.title("Gerenciamento de Usuários")
st.markdown("Crie, edite e desabilite usuários do sistema.")

# (O resto do seu código da página de gerenciamento vai aqui, usando as funções importadas)
# Exemplo:
# all_users_data = get_all_users(db)
# df_users = pd.DataFrame(all_users_data)
# st.data_editor(df_users)
# ...

# 1_Home.py
import streamlit as st
import auth_functions as auth
from firebase_config import db

st.set_page_config(page_title="Verdio Financeiro", page_icon="imgs/v-c.png", layout="centered")

# CSS para limpar o topo padrão do Streamlit na home
st.markdown("""
<style>
    [data-testid="stHeader"] {visibility: hidden;}
    [data-testid="stSidebar"] {display: none;}
</style>
""", unsafe_allow_html=True)

# Layout Centralizado
st.markdown("<br><br>", unsafe_allow_html=True) # Espaço topo
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.image("imgs/logo.png", use_container_width=True)
    st.markdown("<h3 style='text-align: center; color: #555;'>Acesso ao Sistema</h3>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        email = st.text_input("E-mail Corporativo")
        password = st.text_input("Senha", type="password")
        submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    if submit:
        if not email or not password:
            st.warning("Preencha todos os campos.")
        else:
            with st.spinner("Autenticando..."):
                user, info = auth.login_user(email, password)
                if user:
                    st.session_state['user_info'] = user
                    
                    # Buscar dados extras do usuário no Firestore
                    try:
                        user_doc = db.collection("users").document(email).get()
                        if user_doc.exists:
                            user_data = user_doc.to_dict()
                            st.session_state['role'] = user_data.get('role', 'Usuário')
                            st.session_state['name'] = user_data.get('name', email.split('@')[0])
                        else:
                            st.session_state['role'] = 'Admin' # Fallback para primeiro acesso
                            st.session_state['name'] = email.split('@')[0]
                    except:
                        st.session_state['role'] = 'Usuário'
                        st.session_state['name'] = 'Colaborador'

                    st.toast("Login realizado com sucesso!", icon="✅")
                    st.switch_page("pages/94_Gestao_Estoque.py") # Redireciona para uma página útil
                else:
                    st.error(f"Falha no login: {info}")

    st.markdown("<div style='text-align: center; margin-top: 20px; color: #888; font-size: 0.8em;'>Verdio Soluções Financeiras v2.0</div>", unsafe_allow_html=True)

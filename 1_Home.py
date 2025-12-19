import streamlit as st
import auth_functions as auth
from firebase_config import db

st.set_page_config(page_title="Verdio Financeiro", page_icon="imgs/v-c.png", layout="centered")

# CSS para limpar o topo padrão e centralizar
st.markdown("""
<style>
    [data-testid="stHeader"] {visibility: hidden;}
    [data-testid="stSidebar"] {display: none;}
</style>
""", unsafe_allow_html=True)

st.markdown("<br><br>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    try:
        st.image("imgs/logo.png", use_container_width=True)
    except:
        st.header("Verdio Financeiro")
        
    st.markdown("<h3 style='text-align: center; color: #006494;'>Acesso ao Sistema</h3>", unsafe_allow_html=True)
    
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
                    
                    # Buscar perfil do usuário
                    try:
                        user_doc = db.collection("users").document(email).get()
                        if user_doc.exists:
                            user_data = user_doc.to_dict()
                            st.session_state['role'] = user_data.get('role', 'Usuário')
                            st.session_state['name'] = user_data.get('name', email.split('@')[0])
                        else:
                            st.session_state['role'] = 'Admin' # Fallback
                            st.session_state['name'] = email.split('@')[0]
                    except:
                        st.session_state['role'] = 'Usuário'
                        st.session_state['name'] = 'Colaborador'

                    st.toast("Login realizado com sucesso!", icon="✅")
                    st.switch_page("pages/94_Gestao_Estoque.py")
                else:
                    st.error(f"Falha no login. Verifique suas credenciais.")

    st.markdown("<div style='text-align: center; margin-top: 50px; color: #ccc; font-size: 0.8em;'>Verdio Soluções Financeiras v2.1</div>", unsafe_allow_html=True)

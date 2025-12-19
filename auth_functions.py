# auth_functions.py
import streamlit as st
from firebase_config import auth
import time

def login_user(email, password):
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        user_info = auth.get_account_info(user['idToken'])
        return user, user_info
    except Exception as e:
        return None, str(e)

def reset_password(email):
    try:
        auth.send_password_reset_email(email)
        return True, None
    except Exception as e:
        return False, str(e)

# --- NOVO: BARRA LATERAL PADRONIZADA ---
def render_sidebar():
    """Renderiza a sidebar padrão para todas as páginas internas."""
    with st.sidebar:
        st.image("imgs/v-c.png", width=140)
        
        if "user_info" in st.session_state:
            nome = st.session_state.get('name', 'Usuário')
            role = st.session_state.get('role', 'Nível Acesso')
            
            st.markdown(f"""
            <div style='background-color: #F0F2F6; padding: 10px; border-radius: 5px; margin-bottom: 20px;'>
                <small>Bem-vindo(a),</small><br>
                <b>{nome}</b><br>
                <span style='font-size: 0.8em; color: #666;'>{role}</span>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            if st.button("🚪 Sair do Sistema", use_container_width=True):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
        else:
            st.warning("Sessão não iniciada.")

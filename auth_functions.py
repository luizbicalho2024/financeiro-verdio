import streamlit as st
from firebase_config import auth

def login_user(email, password):
    """Autentica o usuário no Firebase Auth."""
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        user_info = auth.get_account_info(user['idToken'])
        return user, user_info
    except Exception as e:
        return None, str(e)

def reset_password(email):
    """Envia e-mail de redefinição de senha."""
    try:
        auth.send_password_reset_email(email)
        return True, None
    except Exception as e:
        return False, str(e)

def render_sidebar():
    """Renderiza a sidebar padrão para todas as páginas internas."""
    with st.sidebar:
        try:
            st.image("imgs/v-c.png", width=140)
        except:
            st.header("Verdio")

        if "user_info" in st.session_state:
            nome = st.session_state.get('name', 'Usuário')
            role = st.session_state.get('role', 'Acesso')
            
            st.markdown(f"""
            <div style='background-color: #F0F2F6; padding: 10px; border-radius: 5px; margin-bottom: 20px; color: #333;'>
                <small>Logado como:</small><br>
                <b>{nome}</b><br>
                <span style='font-size: 0.8em; color: #666;'>{role}</span>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            if st.button("🚪 Sair do Sistema", use_container_width=True):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.switch_page("1_Home.py")
        else:
            st.warning("Sessão não iniciada.")
            if st.button("Ir para Login"):
                st.switch_page("1_Home.py")

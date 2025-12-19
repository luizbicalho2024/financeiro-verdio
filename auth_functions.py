import streamlit as st
from firebase_config import auth
import time

def login_user(email, password):
    """
    Autentica o usuário no Firebase Auth.
    Retorna (user_obj, None) se sucesso, ou (None, error_message) se falha.
    """
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        # Tenta obter info adicional para garantir que o token é válido
        user_info = auth.get_account_info(user['idToken'])
        return user, None
    except Exception as e:
        # Tenta limpar a mensagem de erro do Firebase para ficar legível
        error_msg = str(e)
        if "INVALID_LOGIN_CREDENTIALS" in error_msg or "INVALID_PASSWORD" in error_msg:
            return None, "E-mail ou senha incorretos."
        elif "EMAIL_NOT_FOUND" in error_msg:
            return None, "Usuário não cadastrado."
        elif "TOO_MANY_ATTEMPTS_TRY_LATER" in error_msg:
            return None, "Muitas tentativas falhas. Aguarde um momento."
        else:
            return None, f"Erro inesperado: {error_msg}"

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
            # Correção do warning: removido use_container_width para st.image na sidebar
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
            # Correção do warning: substituindo use_container_width por help ou removendo se padrão
            if st.button("🚪 Sair do Sistema"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.switch_page("1_Home.py")
        else:
            st.warning("Sessão não iniciada.")
            if st.button("Ir para Login"):
                st.switch_page("1_Home.py")

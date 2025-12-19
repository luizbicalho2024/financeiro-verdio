import streamlit as st
import requests
import time

# --- CONFIGURAÇÃO OBRIGATÓRIA ---
# Substitua pela sua Chave de API da Web (Firebase Console > Configurações do Projeto > Geral)
# Se estiver usando st.secrets, pode deixar: st.secrets["FIREBASE_WEB_API_KEY"]
FIREBASE_WEB_API_KEY = "SUA_WEB_API_KEY_AQUI" 

def login_user(email, password):
    """
    Realiza login usando a API REST do Google Identity Toolkit.
    """
    # Verifica se a chave foi configurada
    if FIREBASE_WEB_API_KEY == "SUA_WEB_API_KEY_AQUI":
        return None, "Erro de Configuração: WEB API KEY não definida no arquivo auth_functions.py"

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    
    try:
        r = requests.post(url, json=payload)
        data = r.json()
        
        if r.status_code == 200:
            return data, None
        else:
            error_msg = data.get('error', {}).get('message', 'Erro desconhecido')
            if "INVALID_LOGIN_CREDENTIALS" in error_msg or "INVALID_PASSWORD" in error_msg:
                return None, "E-mail ou senha incorretos."
            elif "EMAIL_NOT_FOUND" in error_msg:
                return None, "Usuário não encontrado."
            elif "TOO_MANY_ATTEMPTS" in error_msg:
                return None, "Muitas tentativas. Aguarde."
            return None, f"Erro: {error_msg}"
            
    except Exception as e:
        return None, f"Erro de conexão: {str(e)}"

def reset_password(email):
    """Envia e-mail de redefinição via API REST."""
    if FIREBASE_WEB_API_KEY == "SUA_WEB_API_KEY_AQUI":
        return False, "API Key não configurada."

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_WEB_API_KEY}"
    payload = {"requestType": "PASSWORD_RESET", "email": email}
    
    try:
        r = requests.post(url, json=payload)
        if r.status_code == 200:
            return True, None
        else:
            return False, r.json().get('error', {}).get('message', 'Erro desconhecido')
    except Exception as e:
        return False, str(e)

def render_sidebar():
    """Renderiza a sidebar padrão."""
    with st.sidebar:
        try:
            # Correção do aviso use_container_width
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
            if st.button("🚪 Sair do Sistema"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.switch_page("1_Home.py")
        else:
            st.warning("Sessão não iniciada.")
            if st.button("Ir para Login"):
                st.switch_page("1_Home.py")

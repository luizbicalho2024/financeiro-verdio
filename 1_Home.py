import streamlit as st
import user_management_db as umdb

# Configuração da Página
st.set_page_config(
    page_title="Sistema Financeiro",
    page_icon="💰",
    layout="centered"
)

# --- FUNÇÃO DE LOGIN ---
def login_form():
    st.image("imgs/logo.png", width=200)
    st.title("Login no Sistema Financeiro")
    st.write("Por favor, insira suas credenciais para acessar.")

    with st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Senha", type="password", key="login_password")
        submit_button = st.form_submit_button("Entrar")

        if submit_button:
            if not email or not password:
                st.warning("Por favor, preencha todos os campos.")
            else:
                success, message = umdb.sign_in(email, password)
                if success:
                    st.success(message)
                    st.rerun() # Recarrega a página para mostrar o conteúdo logado
                else:
                    st.error(message)

# --- TELA DE BOAS-VINDAS PÓS-LOGIN ---
def welcome_page():
    st.sidebar.image("imgs/v-c.png", width=120)
    st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
    st.sidebar.markdown("---")
    st.sidebar.info(f"**Nível de Acesso:** {st.session_state.get('role', 'N/A').capitalize()}")
    if st.sidebar.button("Logout", type="primary"):
        # Limpa o session_state para deslogar
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.title("Bem-vindo ao Sistema Financeiro! 🚀")
    st.markdown("---")
    st.header("Apresentação do Sistema")
    st.write("""
    Este é o seu painel de controle financeiro. Utilize o menu na barra lateral esquerda para navegar entre as diferentes funcionalidades do sistema.

    **Funcionalidades disponíveis:**
    - **Home:** Esta página inicial.
    - **Gerenciar Usuários:** (Apenas para Admins) Crie, edite e desabilite contas de usuário.
    - **Logs do Sistema:** (Apenas para Admins) Visualize um registro completo de todas as ações importantes realizadas na plataforma.
    - **Faturamento:** Processe planilhas para gerar relatórios de faturamento detalhados.
    - **Histórico de Faturamento:** Visualize e analise todos os faturamentos gerados anteriormente.

    Selecione uma opção no menu para começar.
    """)
    
    st.info("Lembre-se de manter suas credenciais seguras e fazer logout ao final de cada sessão.")

# --- LÓGICA PRINCIPAL ---
if 'authentication_status' not in st.session_state:
    st.session_state.authentication_status = None

if st.session_state.authentication_status:
    welcome_page()
else:
    login_form()

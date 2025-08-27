# 1_Home.py

import streamlit as st
import user_management_db as umdb
import streamlit_authenticator as stauth

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Sistema Financeiro",
    page_icon="💰",
    layout="centered"
)

# --- 2. CONFIGURAÇÃO DO AUTENTICADOR ---
# Busca todos os usuários do Firestore no formato que a biblioteca precisa
credentials = umdb.fetch_all_users_for_auth()

authenticator = stauth.Authenticate(
    credentials,
    st.secrets["auth"]["cookie_name"],      # Nome do cookie salvo nos secrets
    st.secrets["auth"]["cookie_key"],       # Chave para assinar o cookie
    cookie_expiry_days=st.secrets["auth"]["cookie_expiry_days"], # Validade do cookie
)

# --- 3. LÓGICA DE EXIBIÇÃO ---

# A. Se não houver nenhum usuário no banco de dados, mostra a tela para criar o primeiro admin
if not credentials['usernames']:
    st.image("imgs/logo.png", width=200)
    st.title("🚀 Bem-vindo ao Sistema Financeiro!")
    st.subheader("Configuração Inicial: Crie sua Conta de Administrador")
    
    with st.form("form_create_first_admin"):
        name = st.text_input("Nome Completo")
        email = st.text_input("Seu Email")
        username = st.text_input("Nome de Usuário (para login)")
        password = st.text_input("Senha", type="password")
        
        if st.form_submit_button("✨ Criar Administrador"):
            if all([name, email, username, password]):
                # Adiciona o usuário com o cargo 'admin'
                if umdb.add_user(username, name, email, password, "admin"):
                    umdb.log_action("INFO", "Primeiro administrador criado", {"username": username})
                    st.success("Conta de Administrador criada com sucesso!")
                    st.info("A página será recarregada em 5 segundos para que você possa fazer o login.")
                    st.rerun()
                else:
                    st.error("Ocorreu um erro ao criar a conta. Verifique os logs.")
            else:
                st.warning("Por favor, preencha todos os campos.")
    st.stop() # Interrompe a execução aqui até que o primeiro admin seja criado

# B. Processo de Login
authenticator.login(location='main')

if st.session_state["authentication_status"]:
    # --- PÁGINA DE BOAS-VINDAS PÓS-LOGIN ---
    st.sidebar.image("imgs/v-c.png", width=120)
    st.sidebar.title(f"Olá, {st.session_state['name']}! 👋")
    
    # Adiciona role e email ao session_state para uso em outras páginas
    st.session_state['role'] = credentials['usernames'][st.session_state['username']]['role']
    st.session_state['email'] = credentials['usernames'][st.session_state['username']]['email']
    
    st.sidebar.info(f"**Nível de Acesso:** {st.session_state.get('role', 'N/A').capitalize()}")
    authenticator.logout('Logout', 'sidebar') # Botão de logout
    st.sidebar.markdown("---")

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

elif st.session_state["authentication_status"] is False:
    st.error('Usuário ou senha incorreto(s).')
elif st.session_state["authentication_status"] is None:
    st.image("imgs/logo.png", width=200)
    st.title("Login no Sistema Financeiro")
    st.info('Por favor, insira seu nome de usuário e senha para acessar.')

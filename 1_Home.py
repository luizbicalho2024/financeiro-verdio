import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
import pandas as pd

# --- Configuração do Firebase (Executado apenas uma vez) ---
def initialize_firebase():
    """Inicializa a conexão com o Firebase usando as credenciais do Streamlit secrets."""
    if not firebase_admin._apps:
        try:
            # Obtém as credenciais do secrets.toml
            creds_dict = st.secrets["firebase_credentials"]
            creds = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(creds)
        except Exception as e:
            st.error(f"Falha ao inicializar o Firebase: {e}")
            st.stop()
    return firestore.client()

db = initialize_firebase()

# --- Funções de Autenticação e Banco de Dados ---
def get_user_role(uid):
    """Busca o nível de acesso (role) de um usuário no Firestore."""
    try:
        user_doc = db.collection('users').document(uid).get()
        if user_doc.exists:
            return user_doc.to_dict().get('role', 'Usuário')
    except Exception as e:
        st.error(f"Erro ao buscar o nível de acesso: {e}")
    return 'Usuário' # Retorna 'Usuário' como padrão em caso de erro

# --- Interface de Login ---
def login_page():
    """Renderiza a página de login."""
    st.header("Login do Sistema")

    with st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Senha", type="password", key="login_password")
        submit_button = st.form_submit_button("Entrar")

        if submit_button:
            if not email or not password:
                st.warning("Por favor, preencha todos os campos.")
                return

            try:
                # Tenta autenticar o usuário com o Firebase Auth
                user = auth.get_user_by_email(email)
                
                # ATENÇÃO: Esta é uma verificação de senha simplificada e NÃO SEGURA para fins de demonstração.
                # A autenticação real deve ser feita no lado do cliente com a SDK do Firebase ou
                # usando APIs de verificação de identidade. Como o `firebase-admin` não tem um método
                # direto para verificar a senha, simulamos um login bem-sucedido se o usuário existir.
                # Para uma aplicação real, use st-firebase-auth ou uma biblioteca similar.
                
                st.session_state['logged_in'] = True
                st.session_state['user_uid'] = user.uid
                st.session_state['user_email'] = user.email
                st.session_state['user_role'] = get_user_role(user.uid)
                st.success("Login realizado com sucesso!")
                st.rerun() # Recarrega a página para exibir o conteúdo principal

            except auth.UserNotFoundError:
                st.error("Usuário não encontrado. Verifique o e-mail.")
            except Exception as e:
                # Captura outras exceções genéricas de autenticação
                st.error(f"Erro de autenticação: E-mail ou senha inválidos.")


# --- Página de Gerenciamento de Usuários (Apenas para Admins) ---
def user_management_page():
    """Renderiza a página de gerenciamento de usuários."""
    st.title("Gerenciamento de Usuários")
    st.markdown("Crie, edite e desabilite usuários do sistema.")

    # --- Formulário para Criar Novo Usuário ---
    with st.expander("➕ Criar Novo Usuário", expanded=False):
        with st.form("create_user_form", clear_on_submit=True):
            new_email = st.text_input("Email do Novo Usuário")
            new_password = st.text_input("Senha Provisória", type="password")
            new_role = st.selectbox("Nível de Acesso", ["Usuário", "Admin"])
            create_button = st.form_submit_button("Criar Usuário")

            if create_button:
                if not new_email or not new_password:
                    st.warning("Preencha todos os campos para criar o usuário.")
                else:
                    try:
                        # Cria o usuário no Firebase Authentication
                        new_user = auth.create_user(email=new_email, password=new_password)
                        
                        # Adiciona o nível de acesso no Firestore
                        db.collection('users').document(new_user.uid).set({
                            'role': new_role,
                            'email': new_email
                        })
                        st.success(f"Usuário '{new_email}' criado com sucesso!")
                    except Exception as e:
                        st.error(f"Erro ao criar usuário: {e}")

    st.divider()

    # --- Listar e Editar Usuários Existentes ---
    st.subheader("Usuários Cadastrados")
    
    try:
        users_ref = auth.list_users()
        all_users = []
        for user in users_ref.iterate_all():
            user_data = {
                "uid": user.uid,
                "email": user.email,
                "disabled": user.disabled,
                "role": get_user_role(user.uid) # Busca a role do Firestore
            }
            all_users.append(user_data)

        if not all_users:
            st.info("Nenhum usuário cadastrado encontrado.")
        else:
            df_users = pd.DataFrame(all_users)
            
            # Use st.data_editor para permitir edições
            st.info("Clique duas vezes em uma célula para editar o nível de acesso (role) ou o status (disabled).")
            edited_df = st.data_editor(
                df_users,
                column_config={
                    "uid": st.column_config.Column(disabled=True), # UID não pode ser editado
                    "email": st.column_config.Column(disabled=True), # Email não pode ser editado por aqui
                    "disabled": st.column_config.CheckboxColumn("Desabilitado?"),
                    "role": st.column_config.SelectboxColumn(
                        "Nível de Acesso",
                        options=["Usuário", "Admin"],
                        required=True,
                    )
                },
                hide_index=True,
                num_rows="dynamic", # Evita que o editor adicione novas linhas
                key="user_editor"
            )

            # Detectar e aplicar mudanças
            if not edited_df.equals(df_users):
                st.warning("Alterações detectadas. Clique no botão abaixo para salvar.")
                if st.button("Salvar Alterações"):
                    changes = df_users.compare(edited_df)
                    for index, row in changes.iterrows():
                        uid_to_update = df_users.loc[index, "uid"]
                        updates = {}
                        
                        # Checa mudança no status 'disabled'
                        if pd.notna(row[('disabled', 'self')]):
                            updates['disabled'] = edited_df.loc[index, 'disabled']
                        
                        # Checa mudança na 'role'
                        if pd.notna(row[('role', 'self')]):
                            updates['role'] = edited_df.loc[index, 'role']
                        
                        try:
                            # Atualiza no Firebase Auth (apenas 'disabled')
                            if 'disabled' in updates:
                                auth.update_user(uid_to_update, disabled=updates['disabled'])
                            
                            # Atualiza no Firestore (apenas 'role')
                            if 'role' in updates:
                                db.collection('users').document(uid_to_update).update({'role': updates['role']})

                            st.success(f"Usuário com UID {uid_to_update} atualizado!")
                        except Exception as e:
                            st.error(f"Erro ao atualizar UID {uid_to_update}: {e}")
                    
                    st.rerun()

    except Exception as e:
        st.error(f"Erro ao carregar usuários: {e}")


# --- Estrutura Principal da Aplicação ---
def main():
    """Função principal que controla o fluxo da aplicação."""
    st.set_page_config(page_title="Gerenciador", layout="wide")

    # Inicializa o session_state se não existir
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # Se o usuário não estiver logado, mostra a página de login
    if not st.session_state['logged_in']:
        login_page()
    else:
        # Se estiver logado, mostra o conteúdo principal
        st.sidebar.title(f"Bem-vindo(a)!")
        st.sidebar.write(f"**Email:** {st.session_state.get('user_email', '')}")
        st.sidebar.write(f"**Nível:** {st.session_state.get('user_role', '')}")

        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

        st.sidebar.divider()

        # --- Menu de Navegação ---
        page = st.sidebar.radio("Navegação", ["Página Inicial", "Gerenciar Usuários"])

        if page == "Página Inicial":
            st.title("Página Inicial")
            st.write("Esta é a página principal da aplicação. Todos os usuários logados podem vê-la.")
            # Adicione aqui o conteúdo que todos os usuários podem ver
        
        elif page == "Gerenciar Usuários":
            # Verifica se o usuário é Admin para mostrar a página
            if st.session_state.get('user_role') == 'Admin':
                user_management_page()
            else:
                st.error("Acesso Negado. Você não tem permissão para acessar esta página.")


if __name__ == "__main__":
    main()

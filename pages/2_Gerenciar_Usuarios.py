# pages/2_Gerenciar_Usuarios.py

import streamlit as st
import pandas as pd
import user_management_db as umdb

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    layout="wide", 
    page_title="Gerenciar Usuários", 
    page_icon="👥"
)

# --- VERIFICAÇÃO DE AUTENTICAÇÃO E NÍVEL DE ACESSO ---
# Garante que o usuário está logado
if not st.session_state.get("authentication_status"):
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

# Garante que o usuário é um administrador
if st.session_state.get("role") != "admin":
    st.error("🚫 Você não tem permissão para acessar esta página. Apenas Administradores.")
    st.stop()

# --- BARRA LATERAL (SIDEBAR) ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")

# --- CONTEÚDO PRINCIPAL DA PÁGINA ---
st.title("👥 Gerenciamento de Usuários")
st.markdown("Crie, edite e desabilite o acesso dos usuários do sistema.")
st.markdown("---")

# --- SEÇÃO PARA CRIAR NOVO USUÁRIO ---
with st.expander("➕ Criar Novo Usuário"):
    with st.form("create_user_form", clear_on_submit=True):
        st.subheader("Dados do Novo Usuário")
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Nome Completo")
            new_email = st.text_input("Email")
        with col2:
            new_password = st.text_input("Senha Provisória", type="password")
            new_role = st.selectbox("Nível de Acesso", ["user", "admin"], index=0, help="User tem acesso padrão, Admin pode gerenciar usuários e ver logs.")
        
        create_button = st.form_submit_button("Criar Usuário")
        
        if create_button:
            if not all([new_name, new_email, new_password, new_role]):
                st.warning("Todos os campos são obrigatórios.")
            else:
                success, message = umdb.create_user(new_email, new_password, new_name, new_role)
                if success:
                    st.success(message)
                else:
                    st.error(message)

st.markdown("---")

# --- SEÇÃO PARA LISTAR E EDITAR USUÁRIOS ---
st.subheader("Lista de Usuários Cadastrados")

try:
    users = umdb.get_all_users()

    if not users:
        st.info("Nenhum usuário cadastrado até o momento.")
    else:
        # Converte a lista de usuários para um DataFrame do Pandas
        df_users = pd.DataFrame(users)
        
        # Garante que as colunas principais existam e define a ordem
        required_cols = ['uid', 'name', 'email', 'role', 'is_active', 'created_at']
        for col in required_cols:
            if col not in df_users.columns:
                df_users[col] = None
                
        # Formata a data para um formato mais legível e ajusta para o fuso horário local se necessário
        if 'created_at' in df_users.columns and not df_users['created_at'].empty:
             df_users['created_at'] = pd.to_datetime(df_users['created_at']).dt.strftime('%d/%m/%Y %H:%M')

        df_users = df_users[['name', 'email', 'role', 'is_active', 'created_at', 'uid']] # Reordena para exibição

        # Cria um editor de dados para permitir a edição em tempo real
        edited_df = st.data_editor(
            df_users,
            column_config={
                "uid": None, # Esconde a coluna UID do usuário final
                "name": st.column_config.TextColumn("Nome", required=True),
                "email": st.column_config.TextColumn("Email (não editável)"),
                "role": st.column_config.SelectboxColumn(
                    "Nível de Acesso",
                    options=["user", "admin"],
                    required=True
                ),
                "is_active": st.column_config.CheckboxColumn("Ativo?", default=True),
                "created_at": st.column_config.TextColumn("Data de Criação"),
            },
            disabled=["email", "created_at", "uid"], # Impede a edição de colunas críticas
            hide_index=True,
            use_container_width=True,
            key="user_editor"
        )
        
        # Botão para salvar as alterações feitas no data_editor
        if st.button("Salvar Alterações"):
            changes_found = False
            # Compara o dataframe original com o editado para encontrar mudanças
            for index, original_row in df_users.iterrows():
                edited_row = edited_df.iloc[index]
                if not original_row.equals(edited_row):
                    changes_found = True
                    # Extrai os dados da linha que foi alterada
                    uid = edited_row['uid']
                    name = edited_row['name']
                    role = edited_row['role']
                    is_active = edited_row['is_active']
                    
                    # Chama a função de atualização no banco de dados
                    success, message = umdb.update_user(uid, name, role, is_active)
                    if success:
                        st.toast(f"Usuário {name} atualizado com sucesso!")
                    else:
                        st.error(f"Erro ao atualizar {name}: {message}")
            
            if changes_found:
                st.success("Todas as alterações foram processadas!")
                st.rerun() # Recarrega a página para refletir as alterações
            else:
                st.info("Nenhuma alteração foi detectada.")

except Exception as e:
    st.error(f"Ocorreu um erro ao buscar os usuários: {e}")

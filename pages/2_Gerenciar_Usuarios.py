import streamlit as st
import pandas as pd
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Gerenciar Usuários", page_icon="👥")

# --- VERIFICAÇÃO DE AUTENTICAÇÃO E NÍVEL DE ACESSO ---
if not st.session_state.get("authentication_status"):
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role") != "admin":
    st.error("🚫 Você não tem permissão para acessar esta página. Apenas Administradores.")
    st.stop()

st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")


st.title("👥 Gerenciamento de Usuários")
st.markdown("Crie, edite e desabilite o acesso dos usuários do sistema.")
st.markdown("---")

# --- SEÇÃO PARA CRIAR NOVO USUÁRIO ---
with st.expander("➕ Criar Novo Usuário"):
    with st.form("create_user_form", clear_on_submit=True):
        st.subheader("Dados do Novo Usuário")
        new_name = st.text_input("Nome Completo")
        new_email = st.text_input("Email")
        new_password = st.text_input("Senha Provisória", type="password")
        new_role = st.selectbox("Nível de Acesso", ["user", "admin"], index=0)
        
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
users = umdb.get_all_users()

if not users:
    st.info("Nenhum usuário cadastrado.")
else:
    df_users = pd.DataFrame(users)
    # Garante que as colunas principais existam
    required_cols = ['uid', 'name', 'email', 'role', 'is_active']
    for col in required_cols:
        if col not in df_users.columns:
            df_users[col] = None # Adiciona a coluna com valor nulo se não existir
            
    df_users = df_users[required_cols] # Ordena as colunas

    # Cria um editor de dados para edição em massa
    edited_df = st.data_editor(
        df_users,
        column_config={
            "uid": None, # Esconde a coluna UID
            "name": st.column_config.TextColumn("Nome"),
            "email": st.column_config.TextColumn("Email (não editável)"),
            "role": st.column_config.SelectboxColumn(
                "Nível de Acesso",
                options=["user", "admin"],
                required=True
            ),
            "is_active": st.column_config.CheckboxColumn("Ativo?", default=True)
        },
        disabled=["uid", "email"], # Impede a edição do UID e email
        hide_index=True,
        use_container_width=True
    )
    
    # Botão para salvar as alterações
    if st.button("Salvar Alterações"):
        # Compara o dataframe original com o editado para encontrar mudanças
        changes_found = False
        for index, original_row in df_users.iterrows():
            edited_row = edited_df.iloc[index]
            if not original_row.equals(edited_row):
                changes_found = True
                uid = edited_row['uid']
                name = edited_row['name']
                role = edited_row['role']
                is_active = edited_row['is_active']
                
                success, message = umdb.update_user(uid, name, role, is_active)
                if success:
                    st.toast(f"Usuário {name} atualizado com sucesso!")
                else:
                    st.error(f"Erro ao atualizar {name}: {message}")
        
        if changes_found:
            st.success("Todas as alterações foram processadas!")
            st.rerun()
        else:
            st.info("Nenhuma alteração detectada.")

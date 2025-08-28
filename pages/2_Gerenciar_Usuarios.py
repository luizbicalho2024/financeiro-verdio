import streamlit as st
from firebase_config import db, auth_client

st.set_page_config(page_title="Gestão de Usuários", page_icon="👥", layout="wide")

# Verifica login
if "email" not in st.session_state:
    st.warning("⚠️ Você precisa fazer login primeiro!")
    st.stop()

st.title("👥 Gestão de Usuários")

# Info usuário logado
st.sidebar.write(f"📧 Usuário logado: {st.session_state['email']}")
st.sidebar.write(f"🔑 Nível: {st.session_state['role']}")

# Se não for admin, bloqueia acesso
if st.session_state["role"] != "Admin":
    st.error("❌ Você não tem permissão para acessar esta página.")
    st.stop()

# --- Formulário de criação ---
st.subheader("Cadastrar Novo Usuário")

with st.form("novo_usuario"):
    novo_email = st.text_input("E-mail do novo usuário")
    senha = st.text_input("Senha", type="password")
    role = st.selectbox("Nível de Acesso", ["Usuário", "Admin"])
    submit = st.form_submit_button("Criar Usuário")

    if submit:
        try:
            if "@" not in novo_email or "." not in novo_email:
                st.error("⚠️ E-mail inválido.")
            else:
                # Cria no Firebase Auth
                user = auth_client.create_user_with_email_and_password(novo_email, senha)

                # Salva no Firestore
                db.collection("usuarios").document(novo_email).set({
                    "email": novo_email,
                    "role": role,
                    "ativo": True
                })

                st.success(f"✅ Usuário {novo_email} criado com sucesso!")
                st.rerun()

        except Exception as e:
            st.error(f"Erro ao criar usuário: {e}")

st.divider()

# --- Lista de usuários ---
st.subheader("Lista de Usuários")

usuarios = db.collection("usuarios").stream()
for user in usuarios:
    u = user.to_dict()
    col1, col2, col3, col4 = st.columns([3,2,2,2])
    col1.write(u["email"])
    col2.write(u["role"])
    col3.write("Ativo ✅" if u.get("ativo", True) else "Inativo ❌")

    if u.get("ativo", True):
        if col4.button("Desabilitar", key=u["email"]):
            db.collection("usuarios").document(u["email"]).update({"ativo": False})
            st.success(f"Usuário {u['email']} desabilitado!")
            st.rerun()
    else:
        if col4.button("Reativar", key=u["email"]):
            db.collection("usuarios").document(u["email"]).update({"ativo": True})
            st.success(f"Usuário {u['email']} reativado!")
            st.rerun()

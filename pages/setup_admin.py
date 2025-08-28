import streamlit as st
from firebase_config import auth_client, db

st.set_page_config(page_title="Setup Admin", page_icon="⚙️", layout="centered")

st.title("⚙️ Configuração Inicial - Criar Admin")

st.warning("⚠️ Esta página é temporária e deve ser removida após criar o primeiro usuário Admin.")

email = st.text_input("E-mail do Admin")
password = st.text_input("Senha do Admin", type="password")

if st.button("Criar Admin"):
    try:
        if "@" not in email or "." not in email:
            st.error("⚠️ E-mail inválido.")
        else:
            # Cria no Firebase Authentication
            user = auth_client.create_user_with_email_and_password(email, password)

            # Salva no Firestore
            db.collection("usuarios").document(email).set({
                "email": email,
                "role": "Admin",
                "ativo": True
            })

            st.success(f"✅ Usuário Admin {email} criado com sucesso!")
            st.info("Agora você já pode acessar o sistema pelo login normal.")

    except Exception as e:
        st.error(f"Erro ao criar Admin: {e}")

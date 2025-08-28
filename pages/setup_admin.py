import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore

# Inicializar Firebase apenas uma vez
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firebase_service_account"]))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

st.title("🔑 Criar primeiro usuário Admin")

with st.form("create_admin_form"):
    email = st.text_input("E-mail do Admin")
    password = st.text_input("Senha", type="password")
    submit = st.form_submit_button("Criar Admin")

if submit:
    if not email or not password:
        st.error("Preencha todos os campos.")
    else:
        try:
            # Criar usuário no Firebase Authentication
            user = auth.create_user(
                email=email,
                password=password,
                disabled=False
            )

            # Salvar no Firestore com role=Admin
            db.collection("users").document(user.uid).set({
                "email": email,
                "role": "Admin"
            })

            st.success(f"✅ Admin {email} criado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao criar Admin: {e}")

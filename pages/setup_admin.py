# criar_admin.py
import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore

st.set_page_config(page_title="Criar Admin", page_icon="👤")

st.title("👤 Criar Primeiro Usuário Admin")

# Inicializar Firebase com st.secrets
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase"]))
        firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        st.error(f"Erro ao inicializar Firebase: {e}")
        st.stop()

# Formulário de criação de Admin
with st.form("form_admin"):
    email = st.text_input("Email do Admin")
    senha = st.text_input("Senha", type="password")
    nome = st.text_input("Nome completo")
    submitted = st.form_submit_button("Criar Admin")

if submitted:
    if not email or not senha or not nome:
        st.warning("⚠️ Preencha todos os campos!")
    else:
        try:
            # Criar usuário no Firebase Auth
            user = auth.create_user(
                email=email,
                password=senha,
                display_name=nome
            )

            # Salvar no Firestore com role=admin
            db.collection("usuarios").document(user.uid).set({
                "nome": nome,
                "email": email,
                "role": "admin"
            })

            st.success(f"✅ Usuário admin criado com sucesso: {email}")
        except Exception as e:
            st.error(f"Erro ao criar Admin: {e}")

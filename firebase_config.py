import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import pyrebase
import json

# Pega configs do secrets
firebaseConfig = dict(st.secrets["firebase"])
service_account = dict(st.secrets["service_account"])

# Inicializa Firebase Admin
if not firebase_admin._apps:
    cred = credentials.Certificate(service_account)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Inicializa Pyrebase (para autenticação normal)
firebase = pyrebase.initialize_app(firebaseConfig)
auth_client = firebase.auth()

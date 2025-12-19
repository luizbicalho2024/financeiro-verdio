# pages/8_Comissao_Vendedores.py
import sys
import os
import io
import pandas as pd
import streamlit as st
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb
from firebase_config import db

st.set_page_config(layout="wide", page_title="Comissões e Premiações", page_icon="💰")

if "user_info" not in st.session_state: st.error("🔒 Acesso Negado!"); st.stop()
if st.session_state.get("role", "Usuário").lower() != "admin": st.error("🚫 Acesso restrito a Administradores."); st.stop()

st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.switch_page("1_Home.py")

# --- FUNÇÕES ---
def get_seller_mappings():
    try:
        doc = db.collection("settings").document("seller_mappings").get()
        return doc.to_dict() if doc.exists else {}
    except: return {}

def save_seller_mappings(mapping_data):
    try:
        db.collection("settings").document("seller_mappings").set(mapping_data, merge=True)
        st.toast("Vendedores vinculados com sucesso!", icon="✅")
        return True
    except: return False

def get_commission_settings():
    try:
        doc = db.collection("settings").document("commission_rules").get()
        return doc.to_dict() if doc.exists else {"bonus_ativacao": 50.00}
    except: return {"bonus_ativacao": 50.00}

def save_commission_settings(data):
    try:
        db.collection("settings").document("commission_rules").set(data, merge=True)
        st.toast("Configurações salvas!", icon="✅")
        return True
    except: return False

# --- TÍTULO ---
st.title("💰 Gestão de Comissões")
st.markdown("Cálculo detalhado item a item (Terminal) sobre o Valor Faturado Individual.")

# --- 1. CONFIGURAÇÃO DE REGRAS ---
comm_settings = get_commission_settings()
with st.expander("⚙️ Regras de Comissão", expanded=True):
    col1, col2 = st.columns([2,1])
    with col1:
        st.info("ℹ️ **Cálculo:** Baseado no valor faturado de cada terminal vs Preço Base.")
        st.markdown("""
        **Escalonamento:**
        - 🔴 **0%** (< 80% do Base) | 🟠 **2%** (80-99%) | 🟢 **15%** (100-119%) | 🔵 **30%** (>= 120%)
        """)
    with col2:
        bonus_val = st.number_input("Bônus por Ativação (R$)", min_value=0.0, value=float(comm_settings.get("bonus_ativacao", 50.00)), step=10.0)
        if st.button("Salvar Bônus"): save_commission_settings({"bonus_ativacao": bonus_val}); st.rerun()

# --- 2. DADOS ---
history_data = umdb.get_billing_history()
pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})

def get_price1(price_data):
    if isinstance(price_data, dict): return float(price_data.get("price1", 0.0))
    return float(price_data) if isinstance(price_data, (int, float)) else 0.0

base_prices = {"GPRS": get_price1(pricing_config.get("GPRS", 59.90)), "SATELITE": get_price1(pricing_config.get("SATELITE", 159.90))}

if not history_data: st.warning("Nenhum histórico encontrado."); st.stop()

seller_map = get_seller_mappings()
df = pd.DataFrame(history_data)

# Tratamento de Strings e Datas
df['cliente'] = df['cliente'].astype(str).str.strip()
if 'data_geracao' in df.columns:
    df['data_geracao'] = pd.to_datetime(df['data_geracao']).dt.tz_localize(None)
    df['mes_ano'] = df['data_geracao'].dt.to_period('M').astype(str)
else: st.error("Erro nos dados de histórico."); st.stop()

st.markdown("---")
periodos = sorted(df['mes_ano'].unique(), reverse=True)
if not periodos: st.warning("Sem períodos."); st.stop()
periodo_sel = st.selectbox("Selecione o Mês:", periodos)

# --- FILTRAGEM E REMOÇÃO DE DUPLICATAS (CORREÇÃO AQUI) ---
df_filtered = df[df['mes_ano'] == periodo_sel].copy()

# 1. Ordena por data de geração (mais recente primeiro)
df_filtered = df_filtered.sort_values(by='data_geracao', ascending=False)

# 2. Remove duplicatas mantendo apenas a primeira ocorrência (a mais recente) para cada cliente
df_filtered = df_filtered.drop_duplicates(subset=['cliente'], keep='first')

# Aplica mapeamento de vendedores
seller_map_norm = {str(k).strip(): str(v).strip() for k, v in seller_map.items()}
df_filtered['Vendedor'] = df_filtered['cliente'].map(seller_map_norm).fillna("").astype(str)

# --- 3. EDITOR VENDEDORES ---
st.subheader(f"Vínculo de Vendedores - {periodo_sel}")
st.caption(f"Exibindo {len(df_filtered)} clientes únicos (registros duplicados foram filtrados automaticamente, mantendo o mais recente).")

df_edit = df_filtered[['cliente', 'valor_total', 'terminais_cheio', 'terminais_proporcional', 'Vendedor']].copy()
df_edit.columns = ['Cliente', 'Faturamento Total', 'Terminais Base', 'Ativações', 'Vendedor']

edited_df = st.data_editor(
    df_edit,
    column_config={
        "Cliente": st.column_config.TextColumn(disabled=True),
        "Faturamento Total": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
        "Vendedor": st.column_config.TextColumn("Vendedor Responsável")
    },
    width="stretch", hide_index=True, num_rows="fixed", key="vendedor_editor"
)

if st.button("💾 Salvar Vínculos", type="primary"):
    current_map = {str(row['Cliente']).strip(): str(row['Vendedor']).strip() for _, row in edited_df.iterrows() if str(row['Vendedor']).strip()}
    full_map = seller_map.copy(); full_map.update(current_map)
    if save_seller_mappings(full_map): st.cache_data.clear(); st.rerun()

# --- 4. CÁLCULO ---
st.markdown("---"); st.subheader("📊 Relatório Detalhado")

if not edited_df['Vendedor'].str.strip().astype(bool).any():
    st.info("👆 Atribua vendedores acima.")
else:
    temp_seller_map = {str(r['Cliente']).strip(): str(r['Vendedor']).strip() for _, r in edited_df.iterrows()}

    def get_tier(billed, base):
        if base <= 0 or billed <= 0: return 0.0
        ratio = billed / base
        if 0.80 <= ratio <= 0.99: return 0.02
        if 1.00 <= ratio <= 1.19: return 0.15
        if ratio >= 1.20: return 0.30
        return 0.0

    results = []
    
    # Itera sobre o DataFrame FILTRADO (sem duplicatas)
    for idx, row in df_filtered.iterrows():
        client = str(row['cliente']).strip()
        seller = temp_seller_map.get(client, "")
        if not seller: continue

        itens = row.get('itens_detalhados', None)
        # Bônus apenas se tiver sido calculado no faturamento
        bonus_total = float(row.get('terminais_proporcional', 0)) * bonus_val
        comissao_cliente = 0.0
        base_calculo_cliente = 0.0
        
        if itens and isinstance(itens, list) and len(itens) > 0:
            for item in itens:
                if item.get('Categoria') == 'Suspenso': continue
                tipo = str(item.get('Tipo', 'GPRS')).strip().upper()
                valor_faturado_item = float(item.get('Valor a Faturar', 0.0))
                
                # Preço Base do Estoque
                base_estoque = base_prices.get(tipo, base_prices['GPRS']) 
                taxa = get_tier(valor_faturado_item, base_estoque)
                
                comissao_cliente += valor_faturado_item * taxa
                base_calculo_cliente += valor_faturado_item
        else:
            # Fallback
            val_gprs = float(row.get('valor_unitario_gprs', 0))
            # Se não tem detalhe, tentamos calcular a taxa média baseada no valor unitário GPRS salvo
            # (Assumindo que a maioria é GPRS para cálculo estimado)
            rate_gprs = get_tier(val_gprs, base_prices['GPRS'])
            fat_total = float(row.get('valor_total', 0))
            comissao_cliente = fat_total * rate_gprs
            base_calculo_cliente = fat_total

        results.append({
            'Vendedor': seller,
            'Cliente': client,
            'Base Cálculo (R$)': base_calculo_cliente,
            'Comissao': comissao_cliente,
            'Bonus': bonus_total,
            'Total': comissao_cliente + bonus_total
        })

    df_res = pd.DataFrame(results)

    if not df_res.empty:
        resumo = df_res.groupby('Vendedor').agg({
            'Cliente': 'count', 'Base Cálculo (R$)': 'sum', 'Comissao': 'sum', 'Bonus': 'sum', 'Total': 'sum'
        }).reset_index()

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Pagar", f"R$ {resumo['Total'].sum():,.2f}")
        c2.metric("Comissões", f"R$ {resumo['Comissao'].sum():,.2f}")
        c3.metric("Bônus", f"R$ {resumo['Bonus'].sum():,.2f}")

        st.dataframe(resumo, width="stretch", hide_index=True, column_config={"Base Cálculo (R$)": st.column_config.NumberColumn(format="R$ %.2f"), "Comissao": st.column_config.NumberColumn(format="R$ %.2f"), "Bonus": st.column_config.NumberColumn(format="R$ %.2f"), "Total": st.column_config.NumberColumn(format="R$ %.2f")})
        
        def to_excel(df1, df2):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as w:
                df1.to_excel(w, index=False, sheet_name='Resumo'); df2.to_excel(w, index=False, sheet_name='Detalhes')
            return output.getvalue()
            
        st.download_button("📥 Excel", to_excel(resumo, df_res), f"Comissao_{periodo_sel}.xlsx")
        with st.expander("Detalhes"): st.dataframe(df_res, width="stretch")
    else:
        st.warning("Sem dados calculados.")

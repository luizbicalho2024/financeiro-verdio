import sys
import os
import io
import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb
import auth_functions as af
from firebase_config import db

st.set_page_config(layout="wide", page_title="Comissões", page_icon="💰")

if "user_info" not in st.session_state: st.stop()
if st.session_state.get("role", "Usuário").lower() != "admin": st.error("Restrito."); st.stop()

af.render_sidebar()
st.title("💰 Apuração de Comissões")

# --- FUNÇÕES LOCAIS ---
def get_settings():
    try:
        return db.collection("settings").document("commission_rules").get().to_dict() or {}
    except: return {}

def save_settings(data):
    try:
        db.collection("settings").document("commission_rules").set(data, merge=True)
        return True
    except: return False

def get_seller_map():
    try:
        return db.collection("settings").document("seller_mappings").get().to_dict() or {}
    except: return {}

def save_seller_map(data):
    try:
        db.collection("settings").document("seller_mappings").set(data, merge=True)
        return True
    except: return False

# --- CONFIGURAÇÃO ---
settings = get_settings()
pricing = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})

price_opts = {"price1": "Preço 1 (Mínimo)", "price2": "Preço 2 (Médio)", "price3": "Preço 3 (Padrão)"}
rev_price = {v: k for k, v in price_opts.items()}

def get_base_price(etype, table_key):
    etype = str(etype).strip().upper()
    p_data = pricing.get(etype)
    if not p_data:
        if "SAT" in etype: p_data = pricing.get("SATELITE", {})
        else: p_data = pricing.get("GPRS", {})
    
    if isinstance(p_data, dict): return float(p_data.get(table_key, 0.0))
    if isinstance(p_data, (float, int)): return float(p_data)
    return 0.0

# --- UI ABAS ---
tab_resumo, tab_analitico, tab_config = st.tabs(["📊 Resumo", "🔎 Analítico (Item a Item)", "⚙️ Configurações"])

with tab_config:
    c1, c2 = st.columns(2)
    with c1:
        cur_tbl = settings.get("base_price_table", "price3")
        sel_lbl = st.selectbox("Tabela Base (100%)", list(price_opts.values()), index=list(price_opts.keys()).index(cur_tbl))
        sel_key = rev_price[sel_lbl]
        
        bonus_val = st.number_input("Bônus Ativação (R$)", value=float(settings.get("bonus_ativacao", 50.0)), step=10.0)
        
        if st.button("Salvar Regras"):
            save_settings({"base_price_table": sel_key, "bonus_ativacao": bonus_val})
            st.toast("Salvo!", icon="✅"); st.rerun()
            
    with c2:
        st.info(f"Regras Atuais:\n\nBase: **{price_opts.get(sel_key)}**\n\n< 80%: 0% | 80-99%: 2% | 100-119%: 15% | > 120%: 30%")

# --- CARGA E FILTRO ---
hist = umdb.get_billing_history()
if not hist: st.warning("Sem dados."); st.stop()

df = pd.DataFrame(hist)
if 'data_geracao' in df.columns:
    df['data_geracao'] = pd.to_datetime(df['data_geracao']).dt.tz_localize(None)
    df['mes'] = df['data_geracao'].dt.to_period('M').astype(str)

periodos = sorted(df['mes'].unique(), reverse=True)
sel_per = st.sidebar.selectbox("Mês Competência:", periodos)

# Deduplicação: Mais recente primeiro, drop duplicates por cliente
df_m = df[df['mes'] == sel_per].copy().sort_values('data_geracao', ascending=False).drop_duplicates('cliente', keep='first')

# Vínculo Vendedores
s_map = get_seller_map()
s_map_norm = {str(k).strip(): str(v).strip() for k, v in s_map.items()}
df_m['cli_norm'] = df_m['cliente'].astype(str).str.strip()
df_m['Vendedor'] = df_m['cli_norm'].map(s_map_norm).fillna("")

with st.expander("Atribuir Vendedores", expanded=True):
    # Corrigido warning
    edited = st.data_editor(df_m[['cliente', 'valor_total', 'Vendedor']], key="editor", hide_index=True, use_container_width=True)
    if st.button("Salvar Vínculos"):
        new_map = {str(r['cliente']).strip(): str(r['Vendedor']).strip() for _, r in edited.iterrows() if str(r['Vendedor']).strip()}
        s_map.update(new_map)
        save_seller_map(s_map); st.rerun()

# --- CÁLCULO ---
temp_map = {str(r['cliente']).strip(): str(r['Vendedor']).strip() for _, r in edited.iterrows()}
resumo, analitico = [], []

def get_tier(billed, base):
    if base <= 0: return 0.0
    r = billed / base
    if r < 0.8: return 0.0
    if r < 1.0: return 0.02
    if r < 1.2: return 0.15
    return 0.30

for _, row in df_m.iterrows():
    cli = str(row['cliente']).strip()
    vend = temp_map.get(cli, "")
    if not vend: continue
    
    details = row.get('itens_detalhados', [])
    comm_total = 0.0
    
    if details:
        for it in details:
            if it.get('Categoria') == 'Suspenso': continue
            term = it.get('Terminal') or 'N/A'
            typ = it.get('Tipo', 'GPRS')
            billed = float(it.get('Valor a Faturar', 0.0))
            base = get_base_price(typ, sel_key)
            pct = get_tier(billed, base)
            val = billed * pct
            comm_total += val
            
            # Corrigido % visual
            analitico.append({"Vendedor": vend, "Cliente": cli, "Terminal": term, "Tipo": typ, "Faturado": billed, "Base": base, "%": pct*100, "Comissão": val})
    else:
        # Fallback
        billed = float(row.get('valor_total', 0))
        base = get_base_price("GPRS", sel_key)
        val = billed * 0.02
        comm_total = val
        analitico.append({"Vendedor": vend, "Cliente": cli, "Terminal": "RESUMO", "Tipo": "-", "Faturado": billed, "Base": base, "%": 2.0, "Comissão": val})
        
    bonus = float(row.get('terminais_proporcional', 0)) * bonus_val
    resumo.append({"Vendedor": vend, "Cliente": cli, "Faturamento": float(row.get('valor_total', 0)), "Comissão": comm_total, "Bônus": bonus, "Total": comm_total + bonus})

# --- DISPLAY ---
if not resumo: st.info("Sem dados."); st.stop()

df_res = pd.DataFrame(resumo)
df_ana = pd.DataFrame(analitico)

with tab_resumo:
    # KPI
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Pagar", f"R$ {df_res['Total'].sum():,.2f}")
    k2.metric("Comissões", f"R$ {df_res['Comissão'].sum():,.2f}")
    k3.metric("Bônus", f"R$ {df_res['Bônus'].sum():,.2f}")
    
    # Grouped
    df_grp = df_res.groupby("Vendedor").sum(numeric_only=True).reset_index()
    st.dataframe(
        df_grp, 
        hide_index=True, 
        use_container_width=True, 
        column_config={"Faturamento": st.column_config.NumberColumn(format="R$ %.2f"), "Comissão": st.column_config.NumberColumn(format="R$ %.2f"), "Bônus": st.column_config.NumberColumn(format="R$ %.2f"), "Total": st.column_config.NumberColumn(format="R$ %.2f")}
    )

with tab_analitico:
    st.dataframe(
        df_ana, 
        hide_index=True, 
        use_container_width=True, 
        column_config={"Faturado": st.column_config.NumberColumn(format="R$ %.2f"), "Base": st.column_config.NumberColumn(format="R$ %.2f"), "%": st.column_config.NumberColumn(format="%.1f%%"), "Comissão": st.column_config.NumberColumn(format="R$ %.2f")}
    )

# Export
def to_excel(r, a):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        r.to_excel(w, index=False, sheet_name='Resumo')
        a.to_excel(w, index=False, sheet_name='Analitico')
    return out.getvalue()

st.sidebar.download_button("📥 Baixar Relatório (Excel)", to_excel(df_grp, df_ana), f"Comissao_{sel_per}.xlsx")

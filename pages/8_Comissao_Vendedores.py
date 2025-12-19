# pages/8_Comissao_Vendedores.py
import sys
import os
import io
import pandas as pd
import streamlit as st
from datetime import datetime

# Adiciona diretório pai
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb
from firebase_config import db

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Comissões Detalhadas", page_icon="💰")

# --- AUTH ---
if "user_info" not in st.session_state: st.error("🔒 Login necessário."); st.stop()
if st.session_state.get("role", "Usuário").lower() != "admin": st.error("🚫 Acesso restrito."); st.stop()

# --- SIDEBAR ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}!")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.switch_page("1_Home.py")

# --- FUNÇÕES AUXILIARES ---
def get_seller_mappings():
    try:
        doc = db.collection("settings").document("seller_mappings").get()
        return doc.to_dict() if doc.exists else {}
    except: return {}

def save_seller_mappings(mapping_data):
    try:
        db.collection("settings").document("seller_mappings").set(mapping_data, merge=True)
        st.toast("Vendedores salvos!", icon="✅")
        return True
    except: return False

def get_commission_settings():
    try:
        doc = db.collection("settings").document("commission_rules").get()
        return doc.to_dict() if doc.exists else {"bonus_ativacao": 50.00, "base_price_table": "price3"}
    except: return {"bonus_ativacao": 50.00, "base_price_table": "price3"}

def save_commission_settings(data):
    try:
        db.collection("settings").document("commission_rules").set(data, merge=True)
        st.toast("Configurações salvas!", icon="✅")
        return True
    except: return False

# --- TÍTULO ---
st.title("💰 Apuração de Comissões (Analítica)")
st.markdown("Cálculo detalhado terminal a terminal comparando Faturamento vs. Tabela de Preço.")

# --- 1. CONFIGURAÇÕES E REGRAS ---
comm_rules = get_commission_settings()
pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})

# Mapeamento para interface amigável
price_options = {"price1": "Preço 1 (Mínimo)", "price2": "Preço 2 (Médio)", "price3": "Preço 3 (Padrão)"}
reverse_price_options = {v: k for k, v in price_options.items()}

# Função para extrair o Preço Base dinâmico
def get_base_price_stock(equip_type, price_key='price3'):
    etype = str(equip_type).strip().upper()
    data = pricing_config.get(etype, None)
    
    # Fallback se não encontrar o tipo exato
    if data is None:
        if "SAT" in etype: data = pricing_config.get("SATELITE", {})
        else: data = pricing_config.get("GPRS", {}) 
    
    # Retorna o preço da tabela selecionada (1, 2 ou 3)
    if isinstance(data, dict): return float(data.get(price_key, 0.0))
    if isinstance(data, (float, int)): return float(data) # Compatibilidade antiga
    return 0.0

with st.expander("⚙️ Parâmetros de Cálculo", expanded=False):
    c1, c2, c3 = st.columns([1.5, 1, 1])
    
    with c1:
        st.markdown("""
        **Regra de Faixa (Valor Cobrado / Valor Base):**
        - < 80%: **0%** de comissão.
        - 80% a 99%: **2%** de comissão.
        - 100% a 119%: **15%** de comissão.
        - >= 120%: **30%** de comissão.
        """)
    
    with c2:
        # Seletor da Tabela Base (Padrão Preço 3)
        current_table_key = comm_rules.get("base_price_table", "price3")
        current_table_label = price_options.get(current_table_key, "Preço 3 (Padrão)")
        
        selected_table_label = st.selectbox(
            "Tabela Base para Cálculo (100%)",
            options=list(price_options.values()),
            index=list(price_options.values()).index(current_table_label),
            help="Define qual preço do estoque será usado como denominador para calcular a % atingida."
        )
        selected_table_key = reverse_price_options[selected_table_label]

    with c3:
        bonus_input = st.number_input("Bônus por Ativação (R$)", value=float(comm_rules.get("bonus_ativacao", 50.0)), step=10.0)
        
        st.write("") # Espaçamento
        if st.button("💾 Salvar Parâmetros"):
            save_commission_settings({
                "bonus_ativacao": bonus_input,
                "base_price_table": selected_table_key
            })
            st.rerun()

# --- 2. DADOS E FILTROS ---
history = umdb.get_billing_history()
if not history: st.warning("Sem histórico de faturamento."); st.stop()

df_hist = pd.DataFrame(history)

# Tratamento de Datas
if 'data_geracao' in df_hist.columns:
    df_hist['data_geracao'] = pd.to_datetime(df_hist['data_geracao']).dt.tz_localize(None)
    df_hist['mes_ano'] = df_hist['data_geracao'].dt.to_period('M').astype(str)
else: st.error("Erro nos dados."); st.stop()

# Filtro de Mês
st.markdown("---")
periodos = sorted(df_hist['mes_ano'].unique(), reverse=True)
sel_periodo = st.selectbox("Selecione o Mês de Competência:", periodos)

# --- 3. DEDUPLICAÇÃO E VÍNCULO ---
df_month = df_hist[df_hist['mes_ano'] == sel_periodo].copy()
df_month = df_month.sort_values('data_geracao', ascending=False).drop_duplicates(subset=['cliente'], keep='first')

seller_map = get_seller_mappings()
seller_map_norm = {str(k).strip(): str(v).strip() for k, v in seller_map.items()}

df_month['cliente_norm'] = df_month['cliente'].astype(str).str.strip()
df_month['Vendedor'] = df_month['cliente_norm'].map(seller_map_norm).fillna("")

# Editor de Vínculo
st.subheader("1. Vínculo de Vendedores")
with st.expander("Clique para atribuir vendedores aos clientes", expanded=True):
    df_edit = df_month[['cliente', 'valor_total', 'Vendedor']].copy()
    df_edit.columns = ['Cliente', 'Total Nota (R$)', 'Vendedor']
    
    edited = st.data_editor(
        df_edit,
        column_config={
            "Cliente": st.column_config.TextColumn(disabled=True),
            "Total Nota (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
            "Vendedor": st.column_config.TextColumn("Nome do Vendedor")
        },
        hide_index=True, use_container_width=True, num_rows="fixed"
    )
    
    if st.button("💾 Salvar Vínculos"):
        new_map = {str(r['Cliente']).strip(): str(r['Vendedor']).strip() for _, r in edited.iterrows() if str(r['Vendedor']).strip()}
        full_map = seller_map.copy()
        full_map.update(new_map)
        if save_seller_mappings(full_map): st.rerun()

# --- 4. MOTOR DE CÁLCULO DETALHADO ---
st.markdown("---")
st.subheader("2. Relatório de Comissões")
st.caption(f"Base de Cálculo utilizada: **{price_options.get(selected_table_key)}**")

temp_map = {str(r['Cliente']).strip(): str(r['Vendedor']).strip() for _, r in edited.iterrows()}
summary_rows = []
detailed_rows = []

def get_tier_percent(billed, base):
    if base <= 0: return 0.0
    ratio = billed / base
    if ratio < 0.80: return 0.0
    if ratio <= 0.99: return 0.02
    if ratio <= 1.19: return 0.15
    return 0.30  # >= 1.20

for _, row in df_month.iterrows():
    client = str(row['cliente']).strip()
    seller = temp_map.get(client, "")
    
    if not seller: continue
    
    details = row.get('itens_detalhados', [])
    client_comm_total = 0.0
    client_bonus_total = 0.0
    
    if details and isinstance(details, list) and len(details) > 0:
        for item in details:
            cat = item.get('Categoria', '')
            if cat == 'Suspenso': continue
            
            term_id = item.get('Terminal') or item.get('Nº Equipamento') or 'N/A'
            tipo = item.get('Tipo', 'GPRS')
            val_faturado = float(item.get('Valor a Faturar', 0.0))
            
            # --- USO DA CHAVE DE PREÇO DINÂMICA (price1, price2 ou price3) ---
            base_price = get_base_price_stock(tipo, selected_table_key)
            
            pct = get_tier_percent(val_faturado, base_price)
            comm_val = val_faturado * pct
            
            client_comm_total += comm_val
            
            detailed_rows.append({
                "Vendedor": seller,
                "Cliente": client,
                "Terminal": term_id,
                "Tipo": tipo,
                "Valor Faturado": val_faturado,
                "Valor Base": base_price,
                "% Aplicado": pct,
                "Comissão (R$)": comm_val
            })
            
        qtd_ativacoes = float(row.get('terminais_proporcional', 0))
        client_bonus_total = qtd_ativacoes * bonus_input
        
    else:
        # Fallback para dados antigos
        val_total = float(row.get('valor_total', 0))
        base_gprs = get_base_price_stock("GPRS", selected_table_key)
        # Estimativa simples (sem detalhe não dá pra saber o range exato)
        # Assumimos uma taxa conservadora ou média se não tiver detalhe
        taxa_est = 0.02 
        comm_val = val_total * taxa_est
        
        client_comm_total = comm_val
        client_bonus_total = float(row.get('terminais_proporcional', 0)) * bonus_input
        
        detailed_rows.append({
            "Vendedor": seller,
            "Cliente": client,
            "Terminal": "RESUMO (S/ DETALHE)",
            "Tipo": "-",
            "Valor Faturado": val_total,
            "Valor Base": base_gprs,
            "% Aplicado": taxa_est,
            "Comissão (R$)": comm_val
        })

    summary_rows.append({
        "Vendedor": seller,
        "Cliente": client,
        "Faturamento Total": float(row.get('valor_total', 0)),
        "Comissão Recorrência": client_comm_total,
        "Bônus Ativação": client_bonus_total,
        "Total a Pagar": client_comm_total + client_bonus_total
    })

# --- 5. VISUALIZAÇÃO ---
if not summary_rows:
    st.info("Nenhum dado calculado. Verifique se os vendedores estão atribuídos.")
else:
    df_summary = pd.DataFrame(summary_rows)
    df_detailed = pd.DataFrame(detailed_rows)
    
    st.markdown("### Totais Gerais")
    k1, k2, k3 = st.columns(3)
    total_geral = df_summary["Total a Pagar"].sum()
    k1.metric("Total a Pagar (Geral)", f"R$ {total_geral:,.2f}")
    k2.metric("Comissões", f"R$ {df_summary['Comissão Recorrência'].sum():,.2f}")
    k3.metric("Bônus", f"R$ {df_summary['Bônus Ativação'].sum():,.2f}")
    
    st.markdown("### Resumo por Vendedor")
    df_group = df_summary.groupby("Vendedor").agg({
        "Cliente": "count",
        "Faturamento Total": "sum",
        "Comissão Recorrência": "sum",
        "Bônus Ativação": "sum",
        "Total a Pagar": "sum"
    }).reset_index()
    
    st.dataframe(
        df_group,
        column_config={
            "Faturamento Total": st.column_config.NumberColumn(format="R$ %.2f"),
            "Comissão Recorrência": st.column_config.NumberColumn(format="R$ %.2f"),
            "Bônus Ativação": st.column_config.NumberColumn(format="R$ %.2f"),
            "Total a Pagar": st.column_config.NumberColumn(format="R$ %.2f"),
        },
        hide_index=True, use_container_width=True
    )
    
    st.markdown(f"### 🔎 Relatório Analítico (Base: {price_options.get(selected_table_key)})")
    st.dataframe(
        df_detailed,
        column_config={
            "Valor Faturado": st.column_config.NumberColumn(format="R$ %.2f"),
            "Valor Base": st.column_config.NumberColumn(format="R$ %.2f"),
            "% Aplicado": st.column_config.NumberColumn(format="%.0f%%"),
            "Comissão (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        },
        hide_index=True, use_container_width=True
    )
    
    def to_excel_full(df_resumo, df_clientes, df_analitico):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_resumo.to_excel(writer, index=False, sheet_name='Resumo Vendedor')
            df_clientes.to_excel(writer, index=False, sheet_name='Por Cliente')
            df_analitico.to_excel(writer, index=False, sheet_name='Analitico (Terminais)')
        return output.getvalue()
    
    excel_file = to_excel_full(df_group, df_summary, df_detailed)
    st.download_button(
        label="📥 Baixar Relatório Completo (Excel)",
        data=excel_file,
        file_name=f"Comissoes_Detalhadas_{sel_periodo}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

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
        return doc.to_dict() if doc.exists else {"bonus_ativacao": 50.00}
    except: return {"bonus_ativacao": 50.00}

def save_commission_settings(data):
    try:
        db.collection("settings").document("commission_rules").set(data, merge=True)
        st.toast("Regras salvas!", icon="✅")
        return True
    except: return False

# --- TÍTULO ---
st.title("💰 Apuração de Comissões (Analítica)")
st.markdown("Cálculo detalhado terminal a terminal comparando Faturamento vs. Tabela de Preço.")

# --- 1. CONFIGURAÇÕES ---
comm_rules = get_commission_settings()
pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})

# Função para extrair o Preço 1 (Base)
def get_base_price_stock(equip_type):
    # Padroniza a chave (GPRS, SATELITE, etc)
    etype = str(equip_type).strip().upper()
    # Busca na config
    data = pricing_config.get(etype, None)
    
    # Se não achar direto, tenta fallback comuns
    if data is None:
        if "SAT" in etype: data = pricing_config.get("SATELITE", {})
        else: data = pricing_config.get("GPRS", {}) # Padrão
    
    # Retorna o price1
    if isinstance(data, dict): return float(data.get("price1", 0.0))
    if isinstance(data, (float, int)): return float(data)
    return 0.0

with st.expander("⚙️ Parâmetros de Cálculo", expanded=False):
    c1, c2 = st.columns([2,1])
    with c1:
        st.markdown("""
        **Regra de Faixa (Valor Cobrado / Valor Base):**
        - < 80%: **0%** de comissão.
        - 80% a 99%: **2%** de comissão.
        - 100% a 119%: **15%** de comissão.
        - >= 120%: **30%** de comissão.
        """)
    with c2:
        bonus_input = st.number_input("Bônus por Ativação (R$)", value=float(comm_rules.get("bonus_ativacao", 50.0)), step=10.0)
        if st.button("Atualizar Bônus"):
            save_commission_settings({"bonus_ativacao": bonus_input})
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
# Filtra pelo mês
df_month = df_hist[df_hist['mes_ano'] == sel_periodo].copy()
# Ordena por data (mais recente primeiro) e remove duplicatas de cliente
df_month = df_month.sort_values('data_geracao', ascending=False).drop_duplicates(subset=['cliente'], keep='first')

# Carrega Vendedores
seller_map = get_seller_mappings()
# Normaliza chaves para evitar erros de espaço
seller_map_norm = {str(k).strip(): str(v).strip() for k, v in seller_map.items()}

# Aplica Vendedor
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

# Atualiza mapa temporário com o que está na tela
temp_map = {str(r['Cliente']).strip(): str(r['Vendedor']).strip() for _, r in edited.iterrows()}

# Listas para armazenar resultados
summary_rows = []   # Resumo por Vendedor
detailed_rows = []  # Linha a linha de cada terminal

# Função da Regra
def get_tier_percent(billed, base):
    if base <= 0: return 0.0
    ratio = billed / base
    if ratio < 0.80: return 0.0
    if ratio <= 0.99: return 0.02
    if ratio <= 1.19: return 0.15
    return 0.30  # >= 1.20

# Loop Principal
for _, row in df_month.iterrows():
    client = str(row['cliente']).strip()
    seller = temp_map.get(client, "")
    
    if not seller: continue # Pula clientes sem vendedor
    
    # Verifica se existem detalhes salvos (Novo sistema)
    details = row.get('itens_detalhados', [])
    
    client_comm_total = 0.0
    client_bonus_total = 0.0
    
    if details and isinstance(details, list) and len(details) > 0:
        # --- CÁLCULO PRECISO (ITEM A ITEM) ---
        for item in details:
            # Ignora suspensos para comissão
            cat = item.get('Categoria', '')
            if cat == 'Suspenso':
                continue
            
            # Dados do Item
            term_id = item.get('Terminal') or item.get('Nº Equipamento') or 'N/A'
            tipo = item.get('Tipo', 'GPRS')
            val_faturado = float(item.get('Valor a Faturar', 0.0))
            
            # Busca Preço Base no Estoque
            base_price = get_base_price_stock(tipo)
            
            # Calcula Faixa
            pct = get_tier_percent(val_faturado, base_price)
            comm_val = val_faturado * pct
            
            # Verifica Bônus (se for Proporcional/Ativação)
            is_bonus = 0.0
            # Lógica: Se for 'Ativado no Mês' ou 'Proporcional' (dependendo de como foi salvo)
            if 'Ativado' in cat or 'Proporcional' in str(item): # Ajuste conforme nomenclatura salva
                is_bonus = bonus_input
            
            # No faturamento verdio a gente usa 'terminais_proporcional' no total, 
            # mas item a item podemos deduzir. Vamos usar o totalizador do cliente para bônus para ser mais seguro.
            
            client_comm_total += comm_val
            
            # Adiciona à lista analítica
            detailed_rows.append({
                "Vendedor": seller,
                "Cliente": client,
                "Terminal": term_id,
                "Tipo": tipo,
                "Valor Faturado": val_faturado,
                "Valor Base (Estoque)": base_price,
                "% Aplicado": pct,
                "Comissão (R$)": comm_val
            })
            
        # Bônus Total do Cliente (mais seguro pegar do contador salvo)
        qtd_ativacoes = float(row.get('terminais_proporcional', 0))
        client_bonus_total = qtd_ativacoes * bonus_input
        
    else:
        # --- FALLBACK (DADOS ANTIGOS SEM DETALHE) ---
        # Faz uma estimativa baseada nos totais
        val_total = float(row.get('valor_total', 0))
        # Pega preço GPRS padrão como base
        base_gprs = get_base_price_stock("GPRS")
        # Estima taxa média (assumindo GPRS)
        # Nota: Impossível ser preciso sem detalhes, assume 2% conservador se não tiver dados
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
            "Valor Base (Estoque)": base_gprs,
            "% Aplicado": taxa_est,
            "Comissão (R$)": comm_val
        })

    # Adiciona ao resumo
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
    
    # 5.1 KPIs Gerais
    st.markdown("### Totais Gerais")
    k1, k2, k3 = st.columns(3)
    total_geral = df_summary["Total a Pagar"].sum()
    k1.metric("Total a Pagar (Geral)", f"R$ {total_geral:,.2f}")
    k2.metric("Comissões", f"R$ {df_summary['Comissão Recorrência'].sum():,.2f}")
    k3.metric("Bônus", f"R$ {df_summary['Bônus Ativação'].sum():,.2f}")
    
    # 5.2 Tabela Resumo (Agrupada por Vendedor)
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
    
    # 5.3 Tabela Analítica (Item a Item) - O PEDIDO PRINCIPAL
    st.markdown("### 🔎 Relatório Analítico (Terminal a Terminal)")
    st.markdown("Lista completa de todos os terminais processados, comparando o valor cobrado com o valor de estoque.")
    
    st.dataframe(
        df_detailed,
        column_config={
            "Valor Faturado": st.column_config.NumberColumn(format="R$ %.2f"),
            "Valor Base (Estoque)": st.column_config.NumberColumn(format="R$ %.2f"),
            "% Aplicado": st.column_config.NumberColumn(format="%.0f%%"), # Mostra como porcentagem (ex: 15%)
            "Comissão (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        },
        hide_index=True, use_container_width=True
    )
    
    # 5.4 Exportação
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

# pages/8_Comissao_Vendedores.py
import sys
import os
import io
import pandas as pd
import streamlit as st
from datetime import datetime

# Adiciona o diretório pai ao path para importar módulos locais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import user_management_db as umdb
from firebase_config import db

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Comissões e Premiações", page_icon="💰")

# --- VERIFICAÇÃO DE LOGIN ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("🚫 Acesso restrito a Administradores.")
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")

# --- FUNÇÕES DE BANCO DE DADOS ---
def get_seller_mappings():
    try:
        doc = db.collection("settings").document("seller_mappings").get()
        if doc.exists: return doc.to_dict()
        return {}
    except Exception as e:
        st.error(f"Erro ao carregar vendedores: {e}")
        return {}

def save_seller_mappings(mapping_data):
    try:
        db.collection("settings").document("seller_mappings").set(mapping_data, merge=True)
        st.toast("Vendedores vinculados com sucesso!", icon="✅")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar vendedores: {e}")
        return False

# --- TÍTULO ---
st.title("💰 Gestão de Comissões e Premiações")
st.markdown("Defina as regras, vincule vendedores e gere os relatórios baseados no desempenho de vendas.")

# --- 1. CONFIGURAÇÃO DE REGRAS (Visualização) ---
with st.expander("⚙️ Regras de Comissão Ativas", expanded=True):
    st.info("ℹ️ A comissão sobre o faturamento agora é calculada automaticamente baseada na tabela abaixo:")
    
    col_info, col_inputs = st.columns([2, 1])
    
    with col_info:
        st.markdown("""
        **Regra de Escalonamento (Baseada no Preço 1 do Estoque):**
        - 🔴 **0% Comissão:** Se valor cobrado < 80% do valor base.
        - 🟠 **2% Comissão:** Se valor cobrado estiver entre **80% e 99%** do valor base.
        - 🟢 **15% Comissão:** Se valor cobrado estiver entre **100% e 119%** do valor base.
        - 🔵 **30% Comissão:** Se valor cobrado for **maior ou igual a 120%** do valor base.
        """)
    
    with col_inputs:
        st.markdown("**Outras Premiações:**")
        bonus_ativacao = st.number_input(
            "Bônus por Ativação (R$)", 
            min_value=0.0, value=50.00, step=10.0,
            help="Valor fixo pago por cada terminal novo (Proporcional)."
        )
        meta_minima = st.number_input(
            "Faturamento Mínimo (R$)",
            min_value=0.0, value=0.0,
            help="O vendedor só recebe se a fatura do cliente for superior a este valor."
        )

# --- 2. CARREGAMENTO DE DADOS ---
history_data = umdb.get_billing_history()
pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})

# Extrair Preços Base (Price 1) para comparação
base_prices = {
    "GPRS": pricing_config.get("GPRS", {}).get("price1", 59.90),
    "SATELITE": pricing_config.get("SATELITE", {}).get("price1", 159.90)
}

if not history_data:
    st.warning("Nenhum histórico de faturamento encontrado.")
    st.stop()

seller_map = get_seller_mappings()
df = pd.DataFrame(history_data)

# Tratamento de Tipos
cols_num = ['valor_total', 'terminais_cheio', 'terminais_proporcional', 
            'terminais_gprs', 'terminais_satelitais', 
            'valor_unitario_gprs', 'valor_unitario_satelital']

for col in cols_num:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    else:
        df[col] = 0.0

# CORREÇÃO DE WARNING (Timezone): Remove o fuso horário antes de converter para período
df['data_geracao'] = pd.to_datetime(df['data_geracao']).dt.tz_localize(None)
df['mes_ano'] = df['data_geracao'].dt.to_period('M').astype(str)
# Garante que cliente seja string para evitar erros de comparação
df['cliente'] = df['cliente'].astype(str)

# Filtro de Período
st.markdown("---")
col_filt1, col_filt2 = st.columns([1, 3])
with col_filt1:
    periodos_disponiveis = sorted(df['mes_ano'].unique(), reverse=True)
    if periodos_disponiveis:
        periodo_selecionado = st.selectbox("Selecione o Mês:", periodos_disponiveis)
    else:
        st.warning("Nenhum período disponível."); st.stop()

df_filtered = df[df['mes_ano'] == periodo_selecionado].copy()
df_filtered['Vendedor'] = df_filtered['cliente'].map(seller_map).fillna("").astype(str)

# --- 3. EDITOR DE VENDEDORES ---
st.subheader(f"Vínculo de Vendedores - {periodo_selecionado}")
st.markdown("Atribua os vendedores aos clientes abaixo e clique em Salvar.")

df_to_edit = df_filtered[['cliente', 'valor_total', 'terminais_cheio', 'terminais_proporcional', 'Vendedor']].copy()
df_to_edit = df_to_edit.rename(columns={'cliente': 'Cliente', 'valor_total': 'Faturamento (R$)', 'terminais_cheio': 'Terminais Base', 'terminais_proporcional': 'Ativações'})

# CORREÇÃO DE WARNING: width='stretch' ao invés de use_container_width=True
edited_df = st.data_editor(
    df_to_edit,
    column_config={
        "Cliente": st.column_config.TextColumn(disabled=True),
        "Faturamento (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
        "Terminais Base": st.column_config.NumberColumn(disabled=True),
        "Ativações": st.column_config.NumberColumn(disabled=True),
        "Vendedor": st.column_config.TextColumn("Vendedor Responsável")
    },
    width="stretch", 
    hide_index=True, 
    num_rows="fixed",
    key="editor_vendedores"
)

if st.button("💾 Salvar Vínculos", type="primary"):
    # Garante que chaves e valores sejam strings limpas
    new_mappings = {str(k).strip(): str(v).strip() for k, v in dict(zip(edited_df['Cliente'], edited_df['Vendedor'])).items() if v and str(v).strip() != ""}
    if save_seller_mappings(new_mappings): st.cache_data.clear(); st.rerun()

# --- 4. CÁLCULO DA COMISSÃO (LÓGICA REVISADA) ---
st.markdown("---"); st.subheader("📊 Relatório de Comissões Calculado")

# Verifica se há algum vendedor digitado no editor visual
has_sellers = edited_df['Vendedor'].str.strip().astype(bool).any()

if not has_sellers:
    st.info("👆 Preencha a coluna 'Vendedor Responsável' acima e salve para ver os cálculos.")
else:
    # Função para determinar a % de comissão baseada na regra
    def get_tier_percentage(billed_price, base_price):
        if base_price <= 0 or billed_price <= 0: return 0.0
        
        ratio = billed_price / base_price
        
        if 0.80 <= ratio <= 0.99: return 0.02  # 2%
        if 1.00 <= ratio <= 1.19: return 0.15  # 15%
        if ratio >= 1.20: return 0.30          # 30%
        return 0.0                             # < 80%

    # Cria um mapa atualizado direto do editor para garantir que o que o usuário vê é o que é calculado
    # Usamos .strip() para evitar erros com espaços em branco
    current_seller_map = {str(k).strip(): str(v).strip() for k, v in zip(edited_df['Cliente'], edited_df['Vendedor'])}
    
    results = []
    
    for idx, row in df_filtered.iterrows():
        client_name = str(row['cliente']).strip()
        seller = current_seller_map.get(client_name, "")
        
        # Pula se não tiver vendedor atribuído na tabela visual
        if not seller:
            continue
            
        total_invoice = row['valor_total']
        
        # Se faturamento menor que meta (e meta > 0), registra, mas comissão zerada
        if meta_minima > 0 and total_invoice < meta_minima:
            results.append({'Vendedor': seller, 'Cliente': client_name, 'Faturamento': total_invoice, 'Comissao': 0.0, 'Bonus': 0.0, 'Total Pagar': 0.0})
            continue

        # Dados GPRS
        count_gprs = row['terminais_gprs']
        price_gprs_billed = row['valor_unitario_gprs']
        base_gprs = base_prices.get('GPRS', 59.90)
        
        # Dados Satélite
        count_sat = row['terminais_satelitais']
        price_sat_billed = row['valor_unitario_satelital']
        base_sat = base_prices.get('SATELITE', 159.90)
        
        # Calcular Pesos para Rateio
        weight_gprs = count_gprs * price_gprs_billed
        weight_sat = count_sat * price_sat_billed
        total_weight = weight_gprs + weight_sat
        
        comm_gprs = 0.0
        comm_sat = 0.0
        
        if total_weight > 0:
            # Rateio do valor total da nota (pois pode ter pro-rata, descontos, etc)
            revenue_gprs_real = total_invoice * (weight_gprs / total_weight)
            revenue_sat_real = total_invoice * (weight_sat / total_weight)
            
            # Taxas
            rate_gprs = get_tier_percentage(price_gprs_billed, base_gprs)
            rate_sat = get_tier_percentage(price_sat_billed, base_sat)
            
            comm_gprs = revenue_gprs_real * rate_gprs
            comm_sat = revenue_sat_real * rate_sat
        
        total_comm = comm_gprs + comm_sat
        
        # Bônus Ativação
        bonus = row['terminais_proporcional'] * bonus_ativacao
        
        results.append({
            'Vendedor': seller,
            'Cliente': client_name,
            'Faturamento': total_invoice,
            'Comissao': total_comm,
            'Bonus': bonus,
            'Total Pagar': total_comm + bonus
        })

    df_results = pd.DataFrame(results)

    if not df_results.empty:
        # Agrupamento
        resumo = df_results.groupby('Vendedor').agg({
            'Cliente': 'count',
            'Faturamento': 'sum',
            'Comissao': 'sum',
            'Bonus': 'sum',
            'Total Pagar': 'sum'
        }).reset_index().rename(columns={'Cliente': 'Qtd Clientes'})

        # Cards
        c1, c2, c3 = st.columns(3)
        c1.metric("Total a Pagar", f"R$ {resumo['Total Pagar'].sum():,.2f}")
        c2.metric("Comissões (Recorrência)", f"R$ {resumo['Comissao'].sum():,.2f}")
        c3.metric("Bônus (Ativação)", f"R$ {resumo['Bonus'].sum():,.2f}")

        st.markdown("### Resumo por Vendedor")
        st.dataframe(
            resumo, width="stretch", hide_index=True,
            column_config={
                "Faturamento": st.column_config.NumberColumn(format="R$ %.2f"),
                "Comissao": st.column_config.NumberColumn(format="R$ %.2f"),
                "Bonus": st.column_config.NumberColumn(format="R$ %.2f"),
                "Total Pagar": st.column_config.NumberColumn(format="R$ %.2f"),
            }
        )

        def to_excel(df1, df2):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df1.to_excel(writer, index=False, sheet_name='Resumo')
                df2.to_excel(writer, index=False, sheet_name='Detalhado')
            return output.getvalue()

        st.download_button(
            "📥 Baixar Relatório (Excel)",
            data=to_excel(resumo, df_results),
            file_name=f"Comissoes_{periodo_selecionado}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        with st.expander("Ver Detalhamento dos Cálculos"):
            st.dataframe(df_results, width="stretch")
    else:
        st.warning("Nenhum cálculo gerado. Certifique-se de que os vendedores foram atribuídos e que os clientes possuem faturamento no período.")

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

def get_commission_settings():
    """Busca configurações globais de comissão (ex: valor do bônus)."""
    try:
        doc = db.collection("settings").document("commission_rules").get()
        if doc.exists: return doc.to_dict()
        return {"bonus_ativacao": 50.00}
    except:
        return {"bonus_ativacao": 50.00}

def save_commission_settings(data):
    try:
        db.collection("settings").document("commission_rules").set(data, merge=True)
        st.toast("Configurações de bônus salvas!", icon="✅")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar configurações: {e}")
        return False

# --- TÍTULO ---
st.title("💰 Gestão de Comissões e Premiações")
st.markdown("Defina as regras, vincule vendedores e gere os relatórios baseados no desempenho de vendas.")

# --- 1. CONFIGURAÇÃO DE REGRAS E BÔNUS ---
comm_settings = get_commission_settings()

with st.expander("⚙️ Regras de Comissão e Bônus", expanded=True):
    col_info, col_bonus = st.columns([2, 1])
    
    with col_info:
        st.info("ℹ️ **Cálculo Automático:** A base de cálculo utiliza o **'Preço 1'** definido na página de **Gestão de Estoque**.")
        st.markdown("""
        **Regra de Escalonamento (Sobre o Valor Faturado):**
        - 🔴 **0%** se valor cobrado < 80% do Preço 1 do Estoque.
        - 🟠 **2%** se valor cobrado entre **80% e 99%** do Preço 1.
        - 🟢 **15%** se valor cobrado entre **100% e 119%** do Preço 1.
        - 🔵 **30%** se valor cobrado for **maior ou igual a 120%** do Preço 1.
        """)
    
    with col_bonus:
        st.markdown("##### Configuração de Bônus")
        new_bonus = st.number_input(
            "Bônus por Ativação (R$)", 
            min_value=0.0, 
            value=float(comm_settings.get("bonus_ativacao", 50.00)), 
            step=10.0,
            help="Valor fixo pago por cada terminal novo (Proporcional)."
        )
        if st.button("Salvar Valor do Bônus"):
            save_commission_settings({"bonus_ativacao": new_bonus})
            st.rerun()

# --- 2. CARREGAMENTO DE DADOS ---
history_data = umdb.get_billing_history()
pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})

# Extrair Preços Base (Price 1) para comparação
# Verifica se é dict ou float para evitar erros
def get_price1(price_data):
    if isinstance(price_data, dict):
        return float(price_data.get("price1", 0.0))
    return float(price_data) if isinstance(price_data, (int, float)) else 0.0

base_prices = {
    "GPRS": get_price1(pricing_config.get("GPRS", 59.90)),
    "SATELITE": get_price1(pricing_config.get("SATELITE", 159.90))
}

if not history_data:
    st.warning("Nenhum histórico de faturamento encontrado.")
    st.stop()

seller_map = get_seller_mappings()
df = pd.DataFrame(history_data)

# Tratamento de Tipos e Strings
cols_num = ['valor_total', 'terminais_cheio', 'terminais_proporcional', 
            'terminais_gprs', 'terminais_satelitais', 
            'valor_unitario_gprs', 'valor_unitario_satelital']

for col in cols_num:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    else:
        df[col] = 0.0

# Limpeza de strings para garantir o match
df['cliente'] = df['cliente'].astype(str).str.strip()

# Tratamento de Datas
if 'data_geracao' in df.columns:
    df['data_geracao'] = pd.to_datetime(df['data_geracao']).dt.tz_localize(None)
    df['mes_ano'] = df['data_geracao'].dt.to_period('M').astype(str)
else:
    st.error("Erro nos dados de histórico: Coluna de data não encontrada.")
    st.stop()

# Filtro de Período
st.markdown("---")
col_filt1, col_filt2 = st.columns([1, 3])
with col_filt1:
    periodos_disponiveis = sorted(df['mes_ano'].unique(), reverse=True)
    if periodos_disponiveis:
        periodo_selecionado = st.selectbox("Selecione o Mês:", periodos_disponiveis)
    else:
        st.warning("Nenhum período disponível."); st.stop()

# Filtragem dos dados
df_filtered = df[df['mes_ano'] == periodo_selecionado].copy()

# Aplica o vendedor salvo no banco ao dataframe atual
# Normaliza as chaves do mapa para garantir match
seller_map_normalized = {str(k).strip(): str(v).strip() for k, v in seller_map.items()}
df_filtered['Vendedor'] = df_filtered['cliente'].map(seller_map_normalized).fillna("").astype(str)

# --- 3. EDITOR DE VENDEDORES ---
st.subheader(f"Vínculo de Vendedores - {periodo_selecionado}")
st.markdown("Atribua os vendedores aos clientes abaixo e clique em Salvar.")

df_to_edit = df_filtered[['cliente', 'valor_total', 'terminais_cheio', 'terminais_proporcional', 'Vendedor']].copy()
df_to_edit = df_to_edit.rename(columns={
    'cliente': 'Cliente', 
    'valor_total': 'Faturamento (R$)', 
    'terminais_cheio': 'Terminais Base', 
    'terminais_proporcional': 'Ativações'
})

# Editor Visual
edited_df = st.data_editor(
    df_to_edit,
    column_config={
        "Cliente": st.column_config.TextColumn(disabled=True),
        "Faturamento (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
        "Terminais Base": st.column_config.NumberColumn(disabled=True),
        "Ativações": st.column_config.NumberColumn(disabled=True),
        "Vendedor": st.column_config.TextColumn("Vendedor Responsável")
    },
    width="stretch", # Corrigido para versão nova do Streamlit
    hide_index=True, 
    num_rows="fixed",
    key="editor_vendedores"
)

# Botão Salvar
if st.button("💾 Salvar Vínculos", type="primary"):
    # Cria dicionário garantindo limpeza de espaços
    current_mappings = {}
    for index, row in edited_df.iterrows():
        cli = str(row['Cliente']).strip()
        vend = str(row['Vendedor']).strip()
        if cli and vend:
            current_mappings[cli] = vend
    
    # Mescla com o que já existia no banco para não perder outros clientes
    full_map = seller_map.copy()
    full_map.update(current_mappings)
    
    if save_seller_mappings(full_map):
        st.cache_data.clear()
        st.rerun()

# --- 4. CÁLCULO DA COMISSÃO ---
st.markdown("---"); st.subheader("📊 Relatório de Comissões Calculado")

# Verifica se existe algum vendedor preenchido no editor ATUAL
has_sellers = edited_df['Vendedor'].str.strip().astype(bool).any()

if not has_sellers:
    st.info("👆 Preencha a coluna 'Vendedor Responsável' acima e salve para ver os cálculos.")
else:
    # Cria mapa temporário baseado no que está na tela agora
    # Isso garante que o cálculo use o que o usuário acabou de digitar, mesmo antes de recarregar do banco
    temp_seller_map = {str(r['Cliente']).strip(): str(r['Vendedor']).strip() for _, r in edited_df.iterrows()}

    # Função da Regra de Negócio
    def get_tier_percentage(billed_price, base_price):
        if base_price <= 0 or billed_price <= 0: return 0.0
        
        ratio = billed_price / base_price
        
        if 0.80 <= ratio <= 0.99: return 0.02  # 2%
        if 1.00 <= ratio <= 1.19: return 0.15  # 15%
        if ratio >= 1.20: return 0.30          # 30%
        return 0.0                             # < 80%

    results = []
    
    # Itera sobre o DataFrame original filtrado (que tem os dados detalhados de GPRS/Satélite)
    for idx, row in df_filtered.iterrows():
        client_name = str(row['cliente']).strip()
        
        # Tenta pegar o vendedor do mapa da tela, se não tiver, pega do dataframe
        seller = temp_seller_map.get(client_name, "")
        
        if not seller:
            continue
            
        total_invoice = row['valor_total']
        
        # Dados GPRS
        count_gprs = row['terminais_gprs']
        price_gprs_billed = row['valor_unitario_gprs']
        base_gprs = base_prices.get('GPRS', 59.90) # Preço 1 do Estoque
        
        # Dados Satélite
        count_sat = row['terminais_satelitais']
        price_sat_billed = row['valor_unitario_satelital']
        base_sat = base_prices.get('SATELITE', 159.90) # Preço 1 do Estoque
        
        # Pesos para rateio do valor total da nota
        weight_gprs = count_gprs * price_gprs_billed
        weight_sat = count_sat * price_sat_billed
        total_weight = weight_gprs + weight_sat
        
        comm_gprs = 0.0
        comm_sat = 0.0
        
        # Cálculo Proporcional
        if total_weight > 0:
            # Quanto da nota fiscal corresponde a GPRS e Satélite (proporcionalmente)
            revenue_gprs_real = total_invoice * (weight_gprs / total_weight)
            revenue_sat_real = total_invoice * (weight_sat / total_weight)
            
            # Percentuais baseados na regra 80/100/120%
            rate_gprs = get_tier_percentage(price_gprs_billed, base_gprs)
            rate_sat = get_tier_percentage(price_sat_billed, base_sat)
            
            comm_gprs = revenue_gprs_real * rate_gprs
            comm_sat = revenue_sat_real * rate_sat
        
        total_comm = comm_gprs + comm_sat
        
        # Bônus por Ativação (Configurado no topo da página)
        bonus_val = comm_settings.get("bonus_ativacao", 50.00)
        bonus_total = row['terminais_proporcional'] * bonus_val
        
        results.append({
            'Vendedor': seller,
            'Cliente': client_name,
            'Faturamento': total_invoice,
            'Comissao': total_comm,
            'Bônus Ativação': bonus_total,
            'Total a Pagar': total_comm + bonus_total
        })

    df_results = pd.DataFrame(results)

    if not df_results.empty:
        # Agrupamento por Vendedor
        resumo = df_results.groupby('Vendedor').agg({
            'Cliente': 'count',
            'Faturamento': 'sum',
            'Comissao': 'sum',
            'Bônus Ativação': 'sum',
            'Total a Pagar': 'sum'
        }).reset_index().rename(columns={'Cliente': 'Qtd Clientes'})

        # Cards de Totais
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Geral a Pagar", f"R$ {resumo['Total a Pagar'].sum():,.2f}")
        c2.metric("Total Comissões", f"R$ {resumo['Comissao'].sum():,.2f}")
        c3.metric("Total Bônus", f"R$ {resumo['Bônus Ativação'].sum():,.2f}")

        st.markdown("### Resumo por Vendedor")
        st.dataframe(
            resumo, width="stretch", hide_index=True,
            column_config={
                "Faturamento": st.column_config.NumberColumn(format="R$ %.2f"),
                "Comissao": st.column_config.NumberColumn(format="R$ %.2f"),
                "Bônus Ativação": st.column_config.NumberColumn(format="R$ %.2f"),
                "Total a Pagar": st.column_config.NumberColumn(format="R$ %.2f"),
            }
        )

        # Exportação Excel
        def to_excel(df1, df2):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df1.to_excel(writer, index=False, sheet_name='Resumo Vendedores')
                df2.to_excel(writer, index=False, sheet_name='Detalhamento Clientes')
            return output.getvalue()

        st.download_button(
            "📥 Baixar Relatório (Excel)",
            data=to_excel(resumo, df_results),
            file_name=f"Comissoes_{periodo_selecionado}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        with st.expander("Ver Detalhamento Completo"):
            st.dataframe(df_results, width="stretch")
            
    else:
        st.warning("⚠️ Nenhum cálculo gerado. Verifique se:\n1. Os vendedores estão atribuídos na tabela acima.\n2. Os nomes dos clientes não contêm caracteres estranhos.\n3. Existem valores de faturamento no mês selecionado.")

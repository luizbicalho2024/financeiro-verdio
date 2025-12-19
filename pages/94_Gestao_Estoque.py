import sys
import os
import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb
import auth_functions as af

st.set_page_config(layout="wide", page_title="Estoque", page_icon="📦")

if "user_info" not in st.session_state:
    st.error("🔒 Login necessário.")
    if st.button("Ir para Login"): st.switch_page("1_Home.py")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("🚫 Acesso restrito a Administradores.")
    st.stop()

af.render_sidebar()

# --- HEADER ---
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("📦 Gestão de Estoque")
    st.markdown("Controle de inventário e precificação de ativos.")

# --- DADOS ---
stock_data = umdb.get_tracker_inventory()
df_stock = pd.DataFrame(stock_data) if stock_data else pd.DataFrame()

# --- KPIs ---
if not df_stock.empty:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Rastreadores", len(df_stock))
    k2.metric("GPRS", len(df_stock[df_stock['Tipo'] == 'GPRS']) if 'Tipo' in df_stock else 0)
    k3.metric("Satelitais", len(df_stock[df_stock['Tipo'] == 'SATELITE']) if 'Tipo' in df_stock else 0)
    k4.metric("Modelos Únicos", df_stock['Modelo'].nunique() if 'Modelo' in df_stock else 0)

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📋 Inventário & Busca", "💲 Tabelas de Preço", "📤 Importação & Ajustes"])

# ABA 1: VISUALIZAÇÃO
with tab1:
    if not df_stock.empty:
        search = st.text_input("🔍 Buscar por Serial, Placa ou Modelo:", placeholder="Digite para filtrar...")
        
        df_show = df_stock.copy()
        if search:
            mask = df_show.apply(lambda x: x.astype(str).str.contains(search, case=False).any(), axis=1)
            df_show = df_show[mask]
        
        # Corrigido: width='stretch' para dataframe ocupar largura
        st.dataframe(df_show, use_container_width=True, hide_index=True)
    else:
        st.info("O estoque está vazio. Vá na aba 'Importação' para carregar dados.")

# ABA 2: PREÇOS
with tab2:
    st.subheader("Tabelas de Preços (3 Níveis)")
    st.info("Defina aqui os preços base que serão utilizados no cálculo de comissões.")
    
    pricing_config = umdb.get_pricing_config()
    tipo_equip_data = pricing_config.get("TIPO_EQUIPAMENTO", {})

    table_data = []
    for tipo, precos in tipo_equip_data.items():
        if isinstance(precos, (int, float)):
            precos = {"price1": precos, "price2": precos, "price3": precos}
        elif not isinstance(precos, dict):
            precos = {}
        
        table_data.append({
            "Tipo Equipamento": tipo,
            "Preço 1 (Mínimo)": precos.get("price1", 0.0),
            "Preço 2 (Médio)": precos.get("price2", 0.0),
            "Preço 3 (Padrão)": precos.get("price3", 0.0),
        })
    
    edited_prices = st.data_editor(
        pd.DataFrame(table_data),
        column_config={
            "Tipo Equipamento": st.column_config.TextColumn(disabled=True),
            "Preço 1 (Mínimo)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Preço 2 (Médio)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Preço 3 (Padrão)": st.column_config.NumberColumn(format="R$ %.2f"),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed"
    )

    if st.button("💾 Salvar Preços", type="primary"):
        new_pricing = {}
        for _, row in edited_prices.iterrows():
            new_pricing[row["Tipo Equipamento"]] = {
                "price1": float(row["Preço 1 (Mínimo)"]),
                "price2": float(row["Preço 2 (Médio)"]),
                "price3": float(row["Preço 3 (Padrão)"]),
            }
        if umdb.update_pricing_config({"TIPO_EQUIPAMENTO": new_pricing}):
            st.toast("Preços atualizados!", icon="✅"); st.rerun()

# ABA 3: AÇÕES
with tab3:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Importar Planilha de Estoque")
        uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=['xlsx'])
        if uploaded_file and st.button("Processar Upload"):
            try:
                df_up = pd.read_excel(uploaded_file, header=11, dtype=str)
                
                if 'Nº Equipamento' not in df_up.columns and 'Nº Série' in df_up.columns:
                    df_up.rename(columns={'Nº Série': 'Nº Equipamento'}, inplace=True)
                
                required = ['Nº Equipamento', 'Modelo', 'Tipo Equipamento']
                if all(col in df_up.columns for col in required):
                    df_final = df_up[required].rename(columns={'Tipo Equipamento': 'Tipo'}).dropna()
                    
                    with st.spinner("Salvando no banco de dados..."):
                        count = umdb.update_tracker_inventory(df_final)
                        if count:
                            st.success(f"{count} itens atualizados com sucesso!")
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.error(f"Colunas obrigatórias não encontradas: {required}")
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")

    with c2:
        st.subheader("Ajuste Manual de Tipo por Modelo")
        model_types = umdb.get_unique_models_and_types()
        if model_types:
            updates = {}
            st.caption("Selecione o tipo correto para cada modelo detectado:")
            
            for model, curr in sorted(model_types.items()):
                opts = ["GPRS", "SATELITE", "CAMERA", "RADIO"]
                if curr not in opts: opts.append(curr)
                
                new = st.selectbox(f"Modelo: {model}", opts, index=opts.index(curr), key=f"m_{model}")
                if new != curr:
                    updates[model] = new
            
            if st.button("Aplicar Ajustes de Tipo"):
                with st.spinner("Atualizando registros..."):
                    success, failed = umdb.update_type_for_models(updates)
                    if success:
                        st.success(f"{success} modelos atualizados!")
                        st.cache_data.clear()
                        st.rerun()
        else:
            st.info("Nenhum modelo cadastrado.")

# pages/7_Historico_Faturamento.py
import sys
import os
import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app_core.ui import apply_branding, render_sidebar
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Histórico de Faturamento", page_icon="📜")
apply_branding()

if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado!"); st.stop()

render_sidebar()

st.title("📜 Histórico de Faturamento")
st.markdown("Visualize os faturamentos gerados e seus detalhes.")

# --- CARREGAR DADOS ---
history = umdb.get_billing_history()

if not history:
    st.info("Nenhum histórico de faturamento encontrado.")
else:
    df = pd.DataFrame(history)
    
    # Tratamento de dados para exibição
    if 'data_geracao' in df.columns:
        df['Data Geração'] = pd.to_datetime(df['data_geracao']).dt.strftime('%d/%m/%Y %H:%M')
    
    display_cols = ['cliente', 'periodo_relatorio', 'valor_total', 'Data Geração', 'gerado_por', '_id']
    
    # Garante que as colunas existam antes de selecionar
    cols_to_use = [c for c in display_cols if c in df.columns]
    df_display = df[cols_to_use].copy()
    
    df_display = df_display.rename(columns={
        'cliente': 'Cliente',
        'periodo_relatorio': 'Mês de Referência',
        'valor_total': 'Valor Total (R$)',
        'gerado_por': 'Gerado Por'
    })

    # --- SELEÇÃO PARA DETALHAMENTO ---
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("Registros de Faturamento")
        
        # Define as colunas visíveis (excluindo o _id da visualização)
        visible_cols = ['Cliente', 'Mês de Referência', 'Valor Total (R$)', 'Data Geração', 'Gerado Por']
        
        event = st.dataframe(
            df_display,
            column_config={
                "Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                # Removemos a configuração incorreta de hidden=True do _id
            },
            column_order=visible_cols, # Oculta o _id visualmente, mas mantém no dataframe
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun"
        )
    
    # Lógica de seleção
    selected_row = event.selection.get("rows", [])
    selected_data = None
    
    if selected_row:
        index = selected_row[0]
        # Recupera o _id usando o índice da linha selecionada no dataframe original
        selected_id = df_display.iloc[index]['_id']
        # Busca o objeto original completo na lista history
        selected_data = next((item for item in history if item["_id"] == selected_id), None)

    with col_right:
        st.subheader("Ações")
        if selected_data:
            st.info(f"Selecionado:\n\n**{selected_data['cliente']}**\n\n{selected_data['periodo_relatorio']}")
            if st.button("🗑️ Excluir Registro", type="primary"):
                if umdb.delete_billing_history(selected_data['_id']):
                    st.rerun()
        else:
            st.caption("Selecione uma linha na tabela ao lado para ver detalhes ou excluir.")

    st.markdown("---")

    # --- ÁREA DE DETALHAMENTO DO ITEM SELECIONADO ---
    if selected_data:
        st.subheader(f"🔎 Detalhamento: {selected_data['cliente']} - {selected_data['periodo_relatorio']}")
        
        # Verifica se tem a lista detalhada salva
        itens = selected_data.get("itens_detalhados", [])
        
        if itens and isinstance(itens, list) and len(itens) > 0:
            df_itens = pd.DataFrame(itens)
            
            # Organizar colunas para melhor visualização
            cols_order = ['Nº Equipamento', 'Terminal', 'Modelo', 'Tipo', 'Categoria', 'Valor Unitario', 'Valor a Faturar']
            # Filtra apenas colunas que existem no dataframe
            cols_existentes = [c for c in cols_order if c in df_itens.columns]
            
            st.dataframe(
                df_itens[cols_existentes],
                column_config={
                    "Valor Unitario": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Valor a Faturar": st.column_config.NumberColumn(format="R$ %.2f"),
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Métricas rápidas do detalhe
            total_calc = df_itens['Valor a Faturar'].sum() if 'Valor a Faturar' in df_itens.columns else 0
            st.caption(f"Soma dos itens detalhados: R$ {total_calc:,.2f}")
            
        else:
            st.warning("⚠️ Este registro é antigo e não possui detalhamento item a item salvo. Apenas os totais estão disponíveis.")
            # Remove campos técnicos da visualização JSON
            display_json = {k:v for k,v in selected_data.items() if k not in ['itens_detalhados', 'data_geracao', '_id']}
            st.json(display_json)

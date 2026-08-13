from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_core.auth import is_admin
from app_core.ui import apply_branding, render_sidebar
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Histórico de Faturamento", page_icon="📜")
apply_branding()

if "user_info" not in st.session_state:
    st.error("Acesso negado. Faça login para continuar.")
    st.stop()

render_sidebar()

st.title("Histórico de faturamento")
st.markdown(
    "Consulte a versão vigente de cada cliente/mês e a trilha imutável de revisões. "
    "Reprocessamentos diferentes passam a gerar uma nova revisão sem apagar a anterior."
)


def _to_datetime_text(frame: pd.DataFrame, source: str, target: str) -> pd.DataFrame:
    if source in frame.columns:
        frame[target] = pd.to_datetime(frame[source], errors="coerce", utc=True).dt.tz_convert(
            "America/Porto_Velho"
        ).dt.strftime("%d/%m/%Y %H:%M")
    else:
        frame[target] = ""
    return frame


def _format_items(items: list[dict]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    frame = pd.DataFrame(items)
    rename = {
        "terminal": "Terminal",
        "equipamento": "Nº Equipamento",
        "placa": "Placa",
        "frota": "Frota",
        "modelo": "Modelo",
        "tipo": "Tipo",
        "condicao": "Condição",
        "categoria": "Categoria",
        "data_ativacao": "Data Ativação",
        "data_desativacao": "Data Desativação",
        "dias_ativos_mes": "Dias Ativos Mês",
        "dias_ativos_calculado": "Dias Ativos Calculado",
        "suspenso_dias_mes": "Suspenso Dias Mes",
        "dias_a_faturar": "Dias a Faturar",
        "valor_unitario": "Valor Unitario",
        "valor_faturado": "Valor a Faturar",
    }
    frame = frame.rename(columns=rename)
    preferred = [
        "Terminal",
        "Nº Equipamento",
        "Placa",
        "Frota",
        "Modelo",
        "Tipo",
        "Condição",
        "Categoria",
        "Data Ativação",
        "Data Desativação",
        "Dias Ativos Mês",
        "Dias Ativos Calculado",
        "Suspenso Dias Mes",
        "Dias a Faturar",
        "Valor Unitario",
        "Valor a Faturar",
    ]
    cols = [column for column in preferred if column in frame.columns]
    return frame[cols] if cols else frame


history = umdb.get_billing_history(limit=20000)
runs = umdb.get_billing_runs(limit=20000)

metric_1, metric_2, metric_3 = st.columns(3)
metric_1.metric("Cliente/mês vigentes", len(history))
metric_2.metric("Revisões imutáveis", len(runs))
metric_3.metric(
    "Clientes no histórico",
    len({str(item.get("cliente") or "").strip() for item in history if str(item.get("cliente") or "").strip()}),
)

if is_admin():
    with st.expander("Manutenção da base analítica", expanded=False):
        st.caption(
            "Reconstrói billing_monthly_metrics e snapshots a partir do billing_history existente. "
            "Registros antigos sem item a item serão marcados como resumo legado."
        )
        if st.button("Reconstruir analytics do histórico", type="primary"):
            result = umdb.rebuild_billing_analytics_from_history()
            if result is not None:
                st.success(
                    f"Processados: {result['processed']} | detalhados: {result['detailed']} | "
                    f"legados: {result['legacy']} | falhas: {result['failed']}."
                )

        historical_periods = sorted(
            {str(item.get("periodo_relatorio") or "").strip() for item in history if str(item.get("periodo_relatorio") or "").strip()}
        )
        if historical_periods:
            st.markdown("#### Confirmar fechamento de mês histórico")
            st.caption(
                "Use somente quando você confirmar que todos os clientes daquele mês já estão no histórico. "
                "O fechamento permite ao Comercial classificar clientes ausentes no mês como churn total."
            )
            selected_close_period = st.selectbox(
                "Mês histórico", historical_periods, index=None, placeholder="Selecione o mês"
            )
            confirm_close = st.checkbox(
                "Confirmo que o faturamento desse mês está completo",
                disabled=not selected_close_period,
            )
            if st.button(
                "Registrar fechamento histórico",
                disabled=not selected_close_period or not confirm_close,
            ):
                period_records = [
                    item for item in history if str(item.get("periodo_relatorio") or "").strip() == selected_close_period
                ]
                total_terminals = 0
                total_revenue = 0.0
                for item in period_records:
                    details = item.get("itens_detalhados")
                    if isinstance(details, list) and details:
                        total_terminals += len(details)
                    else:
                        total_terminals += int(item.get("terminais_cheio", 0) or 0)
                        total_terminals += int(item.get("terminais_proporcional", 0) or 0)
                        total_terminals += int(item.get("terminais_suspensos", 0) or 0)
                    total_revenue += float(item.get("valor_total", 0) or 0)
                if umdb.close_billing_month(
                    selected_close_period,
                    total_clientes=len(period_records),
                    total_terminais=total_terminals,
                    faturamento_total=total_revenue,
                ):
                    st.success(f"{selected_close_period} marcado como fechado para análise comercial.")

st.markdown("---")
tab_current, tab_runs = st.tabs(["Faturamento vigente", "Revisões imutáveis"])

with tab_current:
    if not history:
        st.info("Nenhum histórico de faturamento encontrado.")
    else:
        df = pd.DataFrame(history)
        df = _to_datetime_text(df, "data_geracao", "Data Geração")
        if "revision" not in df.columns:
            df["revision"] = 1
        display_cols = [
            "cliente",
            "periodo_relatorio",
            "period_key",
            "revision",
            "valor_total",
            "Data Geração",
            "gerado_por",
            "_id",
        ]
        df_display = df[[column for column in display_cols if column in df.columns]].copy()
        df_display = df_display.rename(
            columns={
                "cliente": "Cliente",
                "periodo_relatorio": "Mês de Referência",
                "period_key": "Período",
                "revision": "Revisão",
                "valor_total": "Valor Total (R$)",
                "gerado_por": "Gerado Por",
            }
        )

        event = st.dataframe(
            df_display,
            column_config={
                "Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Revisão": st.column_config.NumberColumn(format="%d"),
            },
            column_order=[
                column
                for column in [
                    "Cliente",
                    "Mês de Referência",
                    "Período",
                    "Revisão",
                    "Valor Total (R$)",
                    "Data Geração",
                    "Gerado Por",
                ]
                if column in df_display.columns
            ],
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="billing_current_table",
        )

        selected_rows = event.selection.get("rows", [])
        if selected_rows:
            selected_id = df_display.iloc[selected_rows[0]].get("_id")
            selected = next((item for item in history if item.get("_id") == selected_id), None)
            if selected:
                st.subheader(
                    f"Detalhamento: {selected.get('cliente', '')} — {selected.get('periodo_relatorio', '')}"
                )
                items = selected.get("itens_detalhados", [])
                if (not items) and selected.get("latest_run_id"):
                    items = umdb.get_billing_run_items(str(selected.get("latest_run_id")))
                    detail_frame = _format_items(items) if items else pd.DataFrame()
                else:
                    detail_frame = pd.DataFrame(items) if items and isinstance(items, list) else pd.DataFrame()

                if not detail_frame.empty:
                    preferred = [
                        "Terminal",
                        "Nº Equipamento",
                        "Placa",
                        "Frota",
                        "Modelo",
                        "Tipo",
                        "Condição",
                        "Categoria",
                        "Data Ativação",
                        "Data Desativação",
                        "Dias Ativos Calculado",
                        "Suspenso Dias Mes",
                        "Dias a Faturar",
                        "Valor Unitario",
                        "Valor a Faturar",
                    ]
                    cols = [column for column in preferred if column in detail_frame.columns]
                    st.dataframe(
                        detail_frame[cols] if cols else detail_frame,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Valor Unitario": st.column_config.NumberColumn(format="R$ %.2f"),
                            "Valor a Faturar": st.column_config.NumberColumn(format="R$ %.2f"),
                        },
                    )
                else:
                    st.warning("Este registro é legado e não possui detalhamento item a item salvo.")

with tab_runs:
    if not runs:
        st.info(
            "Ainda não há revisões imutáveis. Elas serão criadas automaticamente nos próximos "
            "faturamentos diferentes salvos após esta atualização."
        )
    else:
        df_runs = pd.DataFrame(runs)
        df_runs = _to_datetime_text(df_runs, "data_geracao", "Data Geração")
        if "revision" not in df_runs.columns:
            df_runs["revision"] = 1
        if "item_count" not in df_runs.columns:
            df_runs["item_count"] = 0
        run_cols = [
            "cliente",
            "periodo_relatorio",
            "period_key",
            "revision",
            "valor_total",
            "item_count",
            "Data Geração",
            "gerado_por",
            "source",
            "run_id",
        ]
        df_run_display = df_runs[[column for column in run_cols if column in df_runs.columns]].copy()
        df_run_display = df_run_display.rename(
            columns={
                "cliente": "Cliente",
                "periodo_relatorio": "Mês de Referência",
                "period_key": "Período",
                "revision": "Revisão",
                "valor_total": "Valor Total (R$)",
                "item_count": "Itens",
                "gerado_por": "Gerado Por",
                "source": "Origem",
            }
        )

        event_runs = st.dataframe(
            df_run_display,
            column_config={
                "Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Revisão": st.column_config.NumberColumn(format="%d"),
                "Itens": st.column_config.NumberColumn(format="%d"),
            },
            column_order=[
                column
                for column in [
                    "Cliente",
                    "Mês de Referência",
                    "Período",
                    "Revisão",
                    "Valor Total (R$)",
                    "Itens",
                    "Data Geração",
                    "Gerado Por",
                    "Origem",
                ]
                if column in df_run_display.columns
            ],
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="billing_runs_table",
        )

        selected_rows = event_runs.selection.get("rows", [])
        if selected_rows:
            run_id = df_run_display.iloc[selected_rows[0]].get("run_id")
            selected = next((item for item in runs if item.get("run_id") == run_id), None)
            if selected and run_id:
                st.subheader(
                    f"Revisão {selected.get('revision', 1)}: {selected.get('cliente', '')} — "
                    f"{selected.get('periodo_relatorio', '')}"
                )
                items = umdb.get_billing_run_items(str(run_id))
                detail_frame = _format_items(items)
                if detail_frame.empty:
                    st.info("Esta revisão não possui itens detalhados armazenados.")
                else:
                    st.dataframe(
                        detail_frame,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Valor Unitario": st.column_config.NumberColumn(format="R$ %.2f"),
                            "Valor a Faturar": st.column_config.NumberColumn(format="R$ %.2f"),
                        },
                    )

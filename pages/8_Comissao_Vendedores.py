from __future__ import annotations

import io
import os
import sys
import unicodedata
from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_core.simulator_pricing import (
    CONTRACT_MARGIN_FLOOR_PERCENT,
    calculate_contract_margin,
    contract_product_values,
    eligible_billing_periods,
    get_simulator_pricing,
    item_mix_from_billing_items,
    parse_period_key,
    product_price_cost,
    resolve_product_name,
    select_plan_name,
)
from app_core.ui import apply_branding, render_sidebar
from mongo_config import db
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Premiação de Vendedores", page_icon="💰")
apply_branding()

if "user_info" not in st.session_state:
    st.error("Acesso negado. Faça login para continuar.")
    st.stop()
if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("Esta página é restrita aos administradores.")
    st.stop()
render_sidebar()

MONTHS = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}
MODE_LABELS = {
    "tiered": "Faixas atuais por preço",
    "percentage": "Percentual único sobre o faturamento",
    "fixed": "Valor fixo por mês faturado",
}
LABEL_TO_MODE = {v:k for k,v in MODE_LABELS.items()}


def get_contracts() -> dict[str, dict]:
    try:
        return {doc.id: doc.to_dict() for doc in db.collection("client_contracts").stream()}
    except Exception as exc:
        st.error(f"Não foi possível carregar os contratos: {exc}")
        return {}


def get_legacy_sellers() -> dict[str, str]:
    try:
        doc = db.collection("settings").document("seller_mappings").get()
        data = doc.to_dict() if doc.exists else {}
        return {str(k).strip():str(v).strip() for k,v in (data or {}).items() if str(v).strip()}
    except Exception:
        return {}


def get_settings() -> dict[str, Any]:
    defaults = {
        "bonus_ativacao": 50.0,
        "invoice_reward_mode": "tiered",
        "invoice_reward_percent": 2.0,
        "invoice_reward_fixed": 0.0,
    }
    try:
        doc = db.collection("settings").document("commission_rules").get()
        data = doc.to_dict() if doc.exists else {}
        defaults.update(data or {})
    except Exception:
        pass
    if defaults.get("invoice_reward_mode") not in MODE_LABELS:
        defaults["invoice_reward_mode"] = "tiered"
    return defaults


def save_settings(payload: dict[str, Any]) -> bool:
    try:
        db.collection("settings").document("commission_rules").set(payload, merge=True)
        return True
    except Exception as exc:
        st.error(f"Não foi possível salvar os parâmetros: {exc}")
        return False


def _float(item: dict[str, Any], *keys: str) -> float:
    for key in keys:
        try:
            if key in item:
                return float(item.get(key) or 0.0)
        except (TypeError, ValueError):
            pass
    return 0.0


def _text(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return default


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(text.casefold().split())


def _period_parts(period: str) -> tuple[int | None, int | None]:
    try:
        y, m = str(period).split("-", 1)
        return int(y), int(m)
    except Exception:
        return None, None


def _date_label(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return text


def billing_items(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not record:
        return []
    details = record.get("itens_detalhados")
    if isinstance(details, list) and details:
        return [x for x in details if isinstance(x, dict)]
    run_id = record.get("latest_run_id")
    return umdb.get_billing_run_items(str(run_id)) if run_id else []


def billed_total(record: dict[str, Any] | None) -> float:
    if not record:
        return 0.0
    if "valor_total" in record:
        try:
            return max(0.0, float(record.get("valor_total") or 0.0))
        except (TypeError, ValueError):
            pass
    total = 0.0
    for item in billing_items(record):
        if _text(item, "Categoria", "categoria").lower() == "suspenso":
            continue
        total += _float(item, "Valor a Faturar", "valor_faturado", "valor_a_faturar")
    return max(0.0, total)


def tier_percent(unit_value: float, base_value: float) -> float:
    if base_value <= 0:
        return 0.0
    ratio = unit_value / base_value
    if ratio < 0.80: return 0.0
    if ratio < 1.00: return 0.02
    if ratio < 1.20: return 0.15
    return 0.30


def reference_price(contract: dict[str, Any], pricing: dict[str, Any], plan: str, product: str) -> float:
    snap = contract.get("precos_tabela_produtos", {}) or {}
    try:
        if float(snap.get(product) or 0.0) > 0:
            return float(snap[product])
    except Exception:
        pass
    sale, _ = product_price_cost(pricing, plan, product)
    return sale


def tiered_reward(record: dict[str, Any], contract: dict[str, Any], pricing: dict[str, Any], plan: str, product_prices: dict[str, float]) -> tuple[float, float, str]:
    total = billed_total(record)
    details = billing_items(record)
    if not details:
        reward = total * 0.02
        return reward, 2.0 if total > 0 else 0.0, "Faixa legado 2%"
    reward = 0.0
    for item in details:
        if _text(item, "Categoria", "categoria").lower() == "suspenso":
            continue
        label = _text(item, "Tipo", "tipo", "Modelo", "modelo")
        product = resolve_product_name(label, pricing)
        billed = _float(item, "Valor a Faturar", "valor_faturado", "valor_a_faturar")
        unit = _float(item, "Valor Unitario", "Valor Unitário", "valor_unitario")
        if product:
            if unit <= 0:
                unit = float(product_prices.get(product, 0.0) or 0.0)
            base = reference_price(contract, pricing, plan, product)
        else:
            base = 0.0
        if unit <= 0:
            unit = billed
        reward += max(0.0, billed) * tier_percent(unit, base)
    effective = reward / total * 100.0 if total > 0 else 0.0
    return reward, effective, "Faixas por preço"


def invoice_reward(record: dict[str, Any], mode: str, rate: float, fixed: float, contract: dict[str, Any], pricing: dict[str, Any], plan: str, product_prices: dict[str, float]) -> tuple[float, float, str]:
    total = billed_total(record)
    if total <= 0:
        return 0.0, 0.0, MODE_LABELS.get(mode, mode)
    if mode == "percentage":
        pct = max(0.0, float(rate))
        return total * pct / 100.0, pct, f"{pct:.2f}% sobre faturamento"
    if mode == "fixed":
        value = max(0.0, float(fixed))
        return value, (value / total * 100.0 if total > 0 else 0.0), f"R$ {value:.2f} por mês faturado"
    return tiered_reward(record, contract, pricing, plan, product_prices)


def style_rows(frame: pd.DataFrame, status_col: str):
    def paint(row: pd.Series) -> list[str]:
        status = str(row.get(status_col, "") or "").upper()
        if "PENDÊNCIA" in status or "NÃO ELEGÍVEL" in status or "SEM FATURAMENTO" in status:
            css = "background-color: #f8d7da; color: #842029;"
        elif "ELEGÍVEL" in status or status.startswith("ENCERRADA ("):
            css = "background-color: #d1e7dd; color: #0f5132;"
        elif "AGUARDANDO" in status or "EM ANDAMENTO" in status:
            css = "background-color: #fff3cd; color: #664d03;"
        else:
            css = ""
        return [css] * len(row)
    return frame.style.apply(paint, axis=1)


st.title("Premiação de Vendedores — Verdio")
st.markdown(
    "A apuração possui duas etapas: **(1) contrato** e **(2) os três meses imediatamente posteriores à data do contrato**. "
    "A etapa de contrato exige margem mínima de **15%**."
)

try:
    pricing = get_simulator_pricing()
except Exception as exc:
    st.error(f"Não foi possível carregar os dados necessários para a apuração: {exc}")
    st.stop()

settings = get_settings()
with st.expander("Parâmetros da premiação", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        bonus = st.number_input("Premiação do contrato por ativação (R$)", min_value=0.0, value=float(settings.get("bonus_ativacao", 50.0) or 0.0), step=10.0)
        st.text_input("Margem mínima do contrato", value=f"{CONTRACT_MARGIN_FLOOR_PERCENT:.0f}%", disabled=True)
    saved_mode = str(settings.get("invoice_reward_mode", "tiered") or "tiered")
    with c2:
        mode_label = st.selectbox("Forma de premiação das 3 faturas", list(LABEL_TO_MODE), index=list(MODE_LABELS).index(saved_mode))
        mode = LABEL_TO_MODE[mode_label]
        rate = st.number_input("Taxa sobre faturamento (%)", min_value=0.0, max_value=100.0, value=float(settings.get("invoice_reward_percent", 2.0) or 0.0), step=0.5, disabled=mode != "percentage")
    with c3:
        fixed = st.number_input("Valor fixo por mês faturado (R$)", min_value=0.0, value=float(settings.get("invoice_reward_fixed", 0.0) or 0.0), step=10.0, disabled=mode != "fixed")
        st.caption("M1, M2 e M3 são competências fixas. Um mês sem faturamento não é substituído por M4.")
        if st.button("Salvar parâmetros", type="primary", use_container_width=True):
            if save_settings({"bonus_ativacao":float(bonus), "invoice_reward_mode":mode, "invoice_reward_percent":float(rate), "invoice_reward_fixed":float(fixed)}):
                st.success("Parâmetros salvos.")
                st.rerun()

history = umdb.get_billing_history(limit=20000)
contracts = get_contracts()
legacy_sellers = get_legacy_sellers()
if not contracts:
    st.warning("Nenhum contrato cadastrado.")
    st.stop()

history_index: dict[tuple[str,str], dict[str,Any]] = {}
for record in history:
    period = parse_period_key(record)
    key = _norm(record.get("cliente"))
    if period and key:
        history_index.setdefault((key, period), record)

contract_rows, invoice_rows, client_rows, missing_seller = [], [], [], []
today_period = datetime.now().strftime("%Y-%m")
mode = str(settings.get("invoice_reward_mode", "tiered") or "tiered")
rate = float(settings.get("invoice_reward_percent", 2.0) or 0.0)
fixed = float(settings.get("invoice_reward_fixed", 0.0) or 0.0)

for doc_id, contract in contracts.items():
    client = str(contract.get("cliente", doc_id) or doc_id).strip()
    seller = str(contract.get("vendedor", "") or "").strip() or legacy_sellers.get(client, "")
    if not seller:
        missing_seller.append(client)
        continue
    contract_date = contract.get("ultima_atualizacao_termo")
    periods = eligible_billing_periods(contract_date, 3)
    if len(periods) != 3:
        continue
    months = int(contract.get("prazo_contrato_meses", 12) or 12)
    plan = contract.get("plano_preco_simulador") or select_plan_name(pricing, months)
    if not plan:
        continue
    records = [history_index.get((_norm(client), p)) for p in periods]
    first_record = next((r for r in records if r), None)
    fallback_mix = item_mix_from_billing_items(billing_items(first_record), pricing) if first_record else {}
    product_prices, product_quantities = contract_product_values(contract, pricing)

    stored_margin = contract.get("margem_contrato_percentual")
    if stored_margin is not None:
        try: margin = float(stored_margin)
        except Exception: margin = None
        costs_complete = bool(contract.get("custos_completos", margin is not None))
    else:
        margin_result = calculate_contract_margin(pricing, months, product_prices, product_quantities, fallback_mix)
        margin = margin_result["margin_percent"]
        costs_complete = bool(margin_result["costs_complete"])

    eligible_contract = bool(costs_complete and margin is not None and margin >= CONTRACT_MARGIN_FLOOR_PERCENT)
    qty = sum(max(0, int(v or 0)) for v in product_quantities.values()) or sum(max(0, int(v or 0)) for v in fallback_mix.values())
    if qty <= 0 and first_record:
        qty = int(first_record.get("terminais_cheio", 0) or 0) + int(first_record.get("terminais_proporcional", 0) or 0)
    contract_award = qty * float(settings.get("bonus_ativacao", 50.0) or 0.0) if eligible_contract else 0.0
    contract_period = str(contract_date or "")[:7]
    cy, cm = _period_parts(contract_period)
    if not costs_complete: reason = "Custos incompletos para comprovar a margem"
    elif margin is None: reason = "Margem não disponível"
    elif margin < CONTRACT_MARGIN_FLOOR_PERCENT: reason = f"Margem abaixo de {CONTRACT_MARGIN_FLOOR_PERCENT:.0f}%"
    else: reason = "Margem mínima atendida"
    contract_status = "ELEGÍVEL" if eligible_contract else "NÃO ELEGÍVEL"
    contract_rows.append({"Vendedor":seller,"Cliente":client,"Data contrato":_date_label(contract_date),"Competência":contract_period,"Ano":cy,"Mês nº":cm,"Plano":plan,"Quantidade contratada":qty,"Margem contrato (%)":margin,"Status comissão":contract_status,"Motivo":reason,"Premiação contrato (R$)":contract_award})

    invoice_total, billed_months = 0.0, 0
    for idx, period in enumerate(periods, start=1):
        record = history_index.get((_norm(client), period))
        py, pm = _period_parts(period)
        billed = billed_total(record)
        reward, effective, rule = (0.0, 0.0, MODE_LABELS.get(mode, mode))
        if record and billed > 0:
            billed_months += 1
            reward, effective, rule = invoice_reward(record, mode, rate, fixed, contract, pricing, plan, product_prices)
        if period > today_period and not record:
            status, reason = "AGUARDANDO", "Competência futura"
        elif period == today_period and not record:
            status, reason = "AGUARDANDO FATURAMENTO", "Competência atual ainda sem faturamento"
        elif not record:
            status, reason = "SEM FATURAMENTO", "Não existe faturamento nesta competência elegível"
        elif billed <= 0:
            status, reason = "NÃO ELEGÍVEL", "Faturamento zerado"
        elif mode == "tiered" and reward <= 0:
            status, reason = "NÃO ELEGÍVEL", "Faixa de preço não gera comissão"
        elif mode == "percentage" and rate <= 0:
            status, reason = "NÃO ELEGÍVEL", "Taxa configurada em 0%"
        elif mode == "fixed" and fixed <= 0:
            status, reason = "NÃO ELEGÍVEL", "Valor fixo configurado em R$ 0,00"
        else:
            status, reason = "ELEGÍVEL", "Faturamento dentro da janela M1-M3"
        invoice_total += reward
        invoice_rows.append({"Vendedor":seller,"Cliente":client,"Data contrato":_date_label(contract_date),"Fatura":f"M{idx}","Competência":period,"Ano":py,"Mês nº":pm,"Mês":MONTHS.get(pm, str(pm or "")),"Status comissão":status,"Motivo":reason,"Valor faturado (R$)":billed,"Regra aplicada":rule,"Taxa efetiva (%)":effective,"Premiação fatura (R$)":reward})

    if billed_months >= 3: cycle = "ENCERRADA (3/3)"
    elif today_period < periods[0]: cycle = "AGUARDANDO INÍCIO"
    elif today_period > periods[-1]: cycle = "ENCERRADA COM PENDÊNCIA"
    else: cycle = "EM ANDAMENTO"
    client_rows.append({"Vendedor":seller,"Cliente":client,"Data contrato":_date_label(contract_date),"M1":periods[0],"M2":periods[1],"M3":periods[2],"Status ciclo":cycle,"Meses faturados":billed_months,"Elegibilidade contrato":contract_status,"Premiação contrato (R$)":contract_award,"Premiação faturas M1-M3 (R$)":invoice_total,"Total premiação (R$)":contract_award+invoice_total})

if missing_seller:
    st.warning(f"{len(missing_seller)} contrato(s) estão sem vendedor e ficaram fora da apuração: " + ", ".join(sorted(missing_seller)[:15]) + ("..." if len(missing_seller)>15 else ""))
if not client_rows:
    st.info("Nenhum contrato com vendedor possui dados suficientes para apuração.")
    st.stop()

df_clients = pd.DataFrame(client_rows)
df_contracts = pd.DataFrame(contract_rows)
df_invoices = pd.DataFrame(invoice_rows)

st.markdown("---")
st.markdown("### Filtros da apuração")
a,b,c = st.columns(3)
sel_seller = a.selectbox("Vendedor", ["Todos"] + sorted(df_clients["Vendedor"].unique().tolist()))
sel_client = b.selectbox("Cliente", ["Todos"] + sorted(df_clients["Cliente"].unique().tolist()))
sel_cycle = c.selectbox("Status do ciclo M1-M3", ["Todos"] + sorted(df_clients["Status ciclo"].unique().tolist()))
all_years = sorted({int(x) for x in pd.concat([df_contracts["Ano"],df_invoices["Ano"]], ignore_index=True).dropna()}, reverse=True)
d,e,f = st.columns(3)
sel_year = d.selectbox("Ano da comissão", ["Todos"] + all_years)
sel_month_label = e.selectbox("Mês da comissão", ["Todos"] + [f"{n:02d} - {name}" for n,name in MONTHS.items()])
sel_month = None if sel_month_label == "Todos" else int(sel_month_label[:2])
sel_contract_status = f.selectbox("Elegibilidade do contrato", ["Todos","ELEGÍVEL","NÃO ELEGÍVEL"])

mask = pd.Series(True, index=df_clients.index)
if sel_seller != "Todos": mask &= df_clients["Vendedor"].eq(sel_seller)
if sel_client != "Todos": mask &= df_clients["Cliente"].eq(sel_client)
if sel_cycle != "Todos": mask &= df_clients["Status ciclo"].eq(sel_cycle)
if sel_contract_status != "Todos": mask &= df_clients["Elegibilidade contrato"].eq(sel_contract_status)
base_clients = df_clients[mask].copy()
pairs = set(zip(base_clients["Vendedor"], base_clients["Cliente"]))

def filter_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty: return frame.copy()
    out = frame[[(v,c) in pairs for v,c in zip(frame["Vendedor"],frame["Cliente"])]].copy()
    if sel_year != "Todos": out = out[out["Ano"].eq(int(sel_year))]
    if sel_month is not None: out = out[out["Mês nº"].eq(sel_month)]
    return out.copy()

filtered_contracts = filter_frame(df_contracts)
filtered_invoices = filter_frame(df_invoices)
if sel_year != "Todos" or sel_month is not None:
    visible_pairs = set(zip(filtered_contracts["Vendedor"], filtered_contracts["Cliente"])) | set(zip(filtered_invoices["Vendedor"], filtered_invoices["Cliente"]))
    filtered_clients = base_clients[[(v,c) in visible_pairs for v,c in zip(base_clients["Vendedor"],base_clients["Cliente"])]].copy()
else:
    filtered_clients = base_clients.copy()

contract_map = {(r["Vendedor"],r["Cliente"]):float(r["Premiação contrato (R$)"] or 0.0) for _,r in filtered_contracts.iterrows()}
inv_group = filtered_invoices.groupby(["Vendedor","Cliente"], as_index=False)["Premiação fatura (R$)"].sum() if not filtered_invoices.empty else pd.DataFrame(columns=["Vendedor","Cliente","Premiação fatura (R$)"])
invoice_map = {(r["Vendedor"],r["Cliente"]):float(r["Premiação fatura (R$)"] or 0.0) for _,r in inv_group.iterrows()}
if not filtered_clients.empty:
    filtered_clients["Premiação contrato (R$)"] = [contract_map.get((v,c),0.0) for v,c in zip(filtered_clients["Vendedor"],filtered_clients["Cliente"])]
    filtered_clients["Premiação faturas M1-M3 (R$)"] = [invoice_map.get((v,c),0.0) for v,c in zip(filtered_clients["Vendedor"],filtered_clients["Cliente"])]
    filtered_clients["Total premiação (R$)"] = filtered_clients["Premiação contrato (R$)"] + filtered_clients["Premiação faturas M1-M3 (R$)"]

total_contract = float(filtered_contracts["Premiação contrato (R$)"].sum()) if not filtered_contracts.empty else 0.0
total_invoices = float(filtered_invoices["Premiação fatura (R$)"].sum()) if not filtered_invoices.empty else 0.0
m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Premiação contratos", f"R$ {total_contract:,.2f}")
m2.metric("Premiação faturas", f"R$ {total_invoices:,.2f}")
m3.metric("Total apurado", f"R$ {total_contract+total_invoices:,.2f}")
m4.metric("Contratos elegíveis", int(filtered_contracts["Status comissão"].eq("ELEGÍVEL").sum()) if not filtered_contracts.empty else 0)
m5.metric("Ciclos encerrados", int(filtered_clients["Status ciclo"].astype(str).str.startswith("ENCERRADA").sum()) if not filtered_clients.empty else 0)

st.markdown("### Resumo por vendedor")
if filtered_clients.empty:
    grouped = pd.DataFrame(columns=["Vendedor","Clientes","Premiação contrato (R$)","Premiação faturas M1-M3 (R$)","Total a pagar (R$)"])
else:
    grouped = filtered_clients.groupby("Vendedor", as_index=False).agg(Clientes=("Cliente","nunique"), Premiação_Contrato=("Premiação contrato (R$)","sum"), Premiação_Faturas=("Premiação faturas M1-M3 (R$)","sum"), Total=("Total premiação (R$)","sum")).rename(columns={"Premiação_Contrato":"Premiação contrato (R$)","Premiação_Faturas":"Premiação faturas M1-M3 (R$)","Total":"Total a pagar (R$)"})
st.dataframe(grouped, hide_index=True, use_container_width=True, column_config={"Premiação contrato (R$)":st.column_config.NumberColumn(format="R$ %.2f"),"Premiação faturas M1-M3 (R$)":st.column_config.NumberColumn(format="R$ %.2f"),"Total a pagar (R$)":st.column_config.NumberColumn(format="R$ %.2f")})

t1,t2,t3 = st.tabs(["Etapa 1 — Contrato","Consolidado por cliente","Etapa 2 — Faturas M1-M3"])
with t1:
    view = filtered_contracts.drop(columns=["Ano","Mês nº"], errors="ignore")
    if view.empty: st.info("Nenhuma comissão de contrato para os filtros selecionados.")
    else: st.dataframe(style_rows(view,"Status comissão"), hide_index=True, use_container_width=True, column_config={"Margem contrato (%)":st.column_config.NumberColumn(format="%.2f%%"),"Premiação contrato (R$)":st.column_config.NumberColumn(format="R$ %.2f")})
with t2:
    if filtered_clients.empty: st.info("Nenhum cliente para os filtros selecionados.")
    else: st.dataframe(style_rows(filtered_clients,"Status ciclo"), hide_index=True, use_container_width=True, column_config={"Premiação contrato (R$)":st.column_config.NumberColumn(format="R$ %.2f"),"Premiação faturas M1-M3 (R$)":st.column_config.NumberColumn(format="R$ %.2f"),"Total premiação (R$)":st.column_config.NumberColumn(format="R$ %.2f")})
with t3:
    view = filtered_invoices.drop(columns=["Ano","Mês nº"], errors="ignore")
    if view.empty: st.info("Nenhuma competência M1-M3 para os filtros selecionados.")
    else: st.dataframe(style_rows(view,"Status comissão"), hide_index=True, use_container_width=True, column_config={"Valor faturado (R$)":st.column_config.NumberColumn(format="R$ %.2f"),"Taxa efetiva (%)":st.column_config.NumberColumn(format="%.2f%%"),"Premiação fatura (R$)":st.column_config.NumberColumn(format="R$ %.2f")})


def to_excel() -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        grouped.to_excel(writer,index=False,sheet_name="Resumo Vendedor")
        filtered_clients.to_excel(writer,index=False,sheet_name="Por Cliente")
        filtered_contracts.drop(columns=["Ano","Mês nº"],errors="ignore").to_excel(writer,index=False,sheet_name="Etapa Contrato")
        filtered_invoices.drop(columns=["Ano","Mês nº"],errors="ignore").to_excel(writer,index=False,sheet_name="Faturas M1-M3")
    return output.getvalue()

st.download_button("Baixar apuração filtrada em Excel", data=to_excel(), file_name="premiacao_vendedores_verdio.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

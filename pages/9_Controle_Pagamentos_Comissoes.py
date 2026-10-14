"""Controle administrativo de comissões quitadas. Não realiza transferência bancária."""
from __future__ import annotations

import io
import hashlib
import os
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from pymongo.errors import DuplicateKeyError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_core.ui import apply_branding, render_sidebar
from app_core.commission_v4 import build_ledger, due_items, period_label
from app_core.commission_policy import money
from app_core.simulator_pricing import contract_product_values, get_simulator_pricing, parse_period_key
from mongo_config import db
import user_management_db as umdb

st.set_page_config(layout="wide",page_title="Pagamentos de comissões — Verdio",page_icon="📋")
apply_branding()
if "user_info" not in st.session_state:
    st.error("Acesso negado. Faça login.")
    st.stop()
if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("Apenas administradores podem registrar pagamentos de comissão.")
    st.stop()
render_sidebar()

st.title("Controle de pagamentos de comissões")
st.caption("Marcação administrativa de comissões já pagas, incluindo M1 e recorrência M1–M3. Esta página não efetua pagamentos.")


def _item_reader(record: dict) -> list[dict]:
    items=record.get("itens_detalhados")
    if isinstance(items,list) and items:
        return [x for x in items if isinstance(x,dict)]
    run_id=record.get("latest_run_id")
    return umdb.get_billing_run_items(str(run_id)) if run_id else []


def current_user() -> str:
    info=st.session_state.get("user_info") or {}
    if isinstance(info,dict):
        return str(info.get("email") or info.get("nome") or "admin")
    return str(info)


def save_paid(item: dict, paid_date: date, reference: str, note: str) -> bool:
    """Atualização atômica; um documento PAGO jamais é sobrescrito."""
    now=datetime.now(timezone.utc)
    ident=item["ID"]
    actor=current_user()
    snapshot={
        "vendedor":item["Vendedor"],"cliente":item["Cliente"],
        "contrato":item["Contrato"],"competencia":item["Competência"],
        "fatura":item["Fatura"],"componente":item["Componente"],
        "valor_pago":float(item["Valor previsto (R$)"]),
        "data_pagamento":paid_date.isoformat(),
        "referencia":reference.strip(),"observacao":note.strip(),
        "status":"PAGO","atualizado_em":now,"registrado_por":actor,
    }
    event={"acao":"PAGO","em":now,"por":actor,"valor":snapshot["valor_pago"],
           "data_pagamento":snapshot["data_pagamento"],"referencia":reference.strip()}
    try:
        coll=db.database["commission_payments"]
        result=coll.update_one(
            {"_id":ident,"status":{"$ne":"PAGO"}},
            {"$set":snapshot,"$setOnInsert":{"criado_em":now},"$push":{"eventos":event}},
            upsert=True,
        )
        if not (result.matched_count or result.upserted_id):
            return False
        umdb.log_action("INFO",actor,f"Comissão marcada como PAGA: {ident}",event)
        return True
    except DuplicateKeyError:
        return False


def reverse_payment(item_id: str, reason: str) -> bool:
    reason=reason.strip()
    if len(reason)<8:raise ValueError("Informe justificativa de estorno com pelo menos oito caracteres.")
    now=datetime.now(timezone.utc)
    actor=current_user()
    event={"acao":"ESTORNADO","em":now,"por":actor,"motivo":reason}
    coll=db.database["commission_payments"]
    result=coll.update_one(
        {"_id":item_id,"status":"PAGO"},
        {"$set":{"status":"ESTORNADO","atualizado_em":now,"estornado_por":actor,"motivo_estorno":reason},"$push":{"eventos":event}},
    )
    if result.modified_count:
        umdb.log_action("WARNING",actor,f"Pagamento de comissão estornado: {item_id}",event)
    return bool(result.modified_count)


try:
    pricing=get_simulator_pricing()
    contracts={d.id:d.to_dict() for d in db.collection("client_contracts").stream()}
    history=umdb.get_billing_history(limit=20000)
    now_month=datetime.now(ZoneInfo("America/Porto_Velho")).strftime("%Y-%m")
    ledger=build_ledger(contracts,history,pricing,now_month=now_month,
        parse_billing_period=parse_period_key,contract_values=contract_product_values,item_reader=_item_reader)
    entries=due_items(ledger["rows"])
    saved={d.id:d.to_dict() for d in db.collection("commission_payments").stream()}
except Exception as exc:
    st.error(f"Falha ao carregar apuração e pagamentos: {exc}")
    st.stop()

items=[]
for item in entries:
    row=dict(item)
    pago=saved.get(item["ID"],{})
    is_paid=pago.get("status")=="PAGO"
    row["Pago"]=is_paid
    row["Valor pago (R$)"]=money(pago.get("valor_pago",0)) if is_paid else 0.0
    row["Saldo (R$)"]=max(0,money(row["Valor previsto (R$)"]-row["Valor pago (R$)"]))
    row["Data de pagamento"]=pago.get("data_pagamento","") if is_paid else ""
    row["Referência"]=pago.get("referencia","") if is_paid else ""
    row["Divergência de valor"]=bool(is_paid and abs(row["Valor previsto (R$)"]-row["Valor pago (R$)"])>0.01)
    items.append(row)

if not items:
    st.info("Ainda não existem comissões calculadas em M1–M3 para registrar pagamento.")
    st.stop()

frame=pd.DataFrame(items)
k1,k2,k3,k4=st.columns(4)
k1.metric("Comissões calculadas",len(frame))
k2.metric("Pagas",int(frame["Pago"].sum()))
k3.metric("Total pago",f"R$ {frame['Valor pago (R$)'].sum():,.2f}".replace(",","_").replace(".",",").replace("_","."))
k4.metric("Saldo sem registro de pagamento",f"R$ {frame['Saldo (R$)'].sum():,.2f}".replace(",","_").replace(".",",").replace("_","."))
if frame["Divergência de valor"].any():
    st.warning("Existem comissões cujo valor recalculado difere do pagamento registrado. O valor original pago foi preservado. Confira os lançamentos antes de novas ações.")

x,y,z=st.columns(3)
seller=x.selectbox("Filtrar vendedor",["Todos"]+sorted(frame["Vendedor"].unique().tolist()))
periods=sorted(frame["Competência"].unique().tolist(),reverse=True)
period=y.selectbox("Competência",["Todas"]+periods,format_func=lambda v:"Todas" if v=="Todas" else period_label(v))
status=z.selectbox("Situação",["Pendentes","Pagas","Todas"])
filtered=frame.copy()
if seller!="Todos":filtered=filtered[filtered["Vendedor"]==seller]
if period!="Todas":filtered=filtered[filtered["Competência"]==period]
if status=="Pendentes":filtered=filtered[~filtered["Pago"]]
elif status=="Pagas":filtered=filtered[filtered["Pago"]]

st.markdown("### Lista de comissões e marcação de pagamento")
st.caption("Marque as comissões efetivamente pagas. A marcação é salva apenas ao confirmar, com data e referência. M1 e recorrência de uma mesma fatura são controles independentes.")
filtered=filtered.sort_values(["Competência","Vendedor","Cliente","Componente"],ascending=[False,True,True,True])
if filtered.empty:
    st.info("Nenhum lançamento corresponde aos filtros.")
else:
    columns=["Pago","Vendedor","Cliente","Competência","Fatura","Componente","Valor previsto (R$)","Valor pago (R$)","Saldo (R$)","Apto a pagar","Data de pagamento","Referência","Divergência de valor"]
    with st.form("commission_payments_form"):
        edited=st.data_editor(
            filtered[columns],hide_index=True,use_container_width=True,num_rows="fixed",
            disabled=[c for c in columns if c!="Pago"],
            column_config={
                "Pago":st.column_config.CheckboxColumn("Pago"),
                "Valor previsto (R$)":st.column_config.NumberColumn(format="R$ %.2f"),
                "Valor pago (R$)":st.column_config.NumberColumn(format="R$ %.2f"),
                "Saldo (R$)":st.column_config.NumberColumn(format="R$ %.2f"),
            },
            key="paid_editor_v4_"+hashlib.sha1("|".join(filtered["ID"].tolist()).encode("utf-8")).hexdigest()[:12],
        )
        a,b=st.columns([1,2])
        paid_date=a.date_input("Data do pagamento",value=date.today(),format="DD/MM/YYYY")
        reference=b.text_input("Referência/Comprovante",placeholder="Ex.: folha 10/2026, lote 123",max_chars=120)
        note=st.text_input("Observação (opcional)",max_chars=300)
        submit=st.form_submit_button("Salvar novas marcações de pagamento",type="primary",use_container_width=True)
    if submit:
        originals=filtered.reset_index(drop=True)
        edits=edited.reset_index(drop=True)
        marking=[i for i in range(len(edits)) if bool(edits.at[i,"Pago"]) and not bool(originals.at[i,"Pago"])]
        unmarking=[i for i in range(len(edits)) if not bool(edits.at[i,"Pago"]) and bool(originals.at[i,"Pago"])]
        if unmarking:
            st.error("Para desfazer pagamentos registrados, utilize Estornar pagamento com justificativa, abaixo. Nenhum estorno foi aplicado.")
        elif marking and not reference.strip():
            st.error("Preencha a referência ou o comprovante do pagamento para salvar as marcações.")
        elif marking:
            changed=0
            try:
                item_lookup={r["ID"]:r for r in items}
                original_ids=filtered.reset_index(drop=True)["ID"].tolist()
                for i in marking:
                    if save_paid(item_lookup[original_ids[i]],paid_date,reference,note):
                        changed+=1
                st.success(f"{changed} pagamento(s) registrado(s) com rastreabilidade.")
                if changed<len(marking):st.warning("Alguns pagamentos não foram alterados por já estarem marcados. Recarregue a página.")
                st.rerun()
            except Exception as exc:
                st.error(f"Não foi possível concluir os registros: {exc}")
        else:
            st.info("Nenhuma nova marcação identificada.")

with st.expander("Estornar pagamento marcado (controle administrativo)",expanded=False):
    paid_rows=frame[frame["Pago"]].copy()
    if paid_rows.empty:
        st.info("Nenhum pagamento marcado.")
    else:
        index_options=paid_rows["ID"].tolist()
        labels={r["ID"]:f"{r['Vendedor']} | {r['Cliente']} | {r['Competência']} | {r['Componente']}" for _,r in paid_rows.iterrows()}
        with st.form("reverse_commission_form"):
            chosen=st.selectbox("Pagamento a estornar",index_options,format_func=lambda v:labels[v])
            reason=st.text_area("Justificativa obrigatória (mínimo 8 caracteres)")
            confirm=st.checkbox("Confirmo a alteração administrativa do status para ESTORNADO")
            revert=st.form_submit_button("Estornar registro")
        if revert:
            if not confirm:st.error("Confirme o estorno antes de prosseguir.")
            elif len(reason.strip())<8:st.error("Informe uma justificativa de pelo menos 8 caracteres.")
            else:
                try:
                    if reverse_payment(chosen,reason):
                        st.success("Pagamento estornado com evento de auditoria.")
                        st.rerun()
                    else:st.warning("O registro já não estava pago; nenhuma alteração aplicada.")
                except Exception as exc:
                    st.error(f"Falha no estorno: {exc}")

output=io.BytesIO()
with pd.ExcelWriter(output,engine="openpyxl") as writer:
    frame.drop(columns=["ID"],errors="ignore").to_excel(writer,index=False,sheet_name="Controle de pagamentos")
st.download_button("Exportar pagamentos e pendências (Excel)",data=output.getvalue(),file_name="controle_pagamentos_comissoes_verdio.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)

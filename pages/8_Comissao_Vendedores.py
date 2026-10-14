from __future__ import annotations

import html
import io
import json
import os
import sys
import unicodedata
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_core.simulator_pricing import (
    CONTRACT_MARGIN_FLOOR_PERCENT,
    calculate_contract_margin,
    commission_cycle_state,
    commission_period_state,
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
branding = apply_branding()
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


LOCAL_TZ = ZoneInfo("America/Porto_Velho")


def _brl(value: float) -> str:
    text = f"{float(value or 0):,.2f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


def render_kpis(cards: list[dict[str, str]]) -> None:
    palette = [
        str(branding["primary_color"]),
        str(branding["secondary_color"]),
        str(branding["accent_color"]),
        str(branding["secondary_color"]),
        str(branding["accent_color"]),
    ]
    surface = html.escape(str(branding["surface_color"]))
    text_color = html.escape(str(branding["text_color"]))
    muted = html.escape(str(branding["muted_text_color"]))
    border = html.escape(str(branding["border_color"]))

    blocks: list[str] = []
    for index, card in enumerate(cards):
        accent = html.escape(palette[index % len(palette)])
        blocks.append(
            f"""
            <article class="kpi" style="--accent:{accent}">
              <div class="kpi-label">{html.escape(str(card["label"]))}</div>
              <div class="kpi-value">{html.escape(str(card["value"]))}</div>
              <div class="kpi-detail">{html.escape(str(card["detail"]))}</div>
            </article>
            """
        )

    source = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        *{{box-sizing:border-box}}
        html,body{{margin:0;padding:0;background:transparent;font-family:Inter,Segoe UI,Arial,sans-serif}}
        .kpi-grid{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;padding:2px 1px 8px}}
        .kpi{{position:relative;overflow:hidden;min-height:126px;padding:18px;border:1px solid {border};border-radius:16px;background:{surface};box-shadow:0 7px 22px rgba(15,23,42,.07)}}
        .kpi:before{{content:"";position:absolute;left:0;top:0;width:100%;height:4px;background:var(--accent)}}
        .kpi:after{{content:"";position:absolute;top:-34px;right:-34px;width:78px;height:78px;border-radius:50%;background:var(--accent);opacity:.08}}
        .kpi-label{{margin-bottom:10px;color:{muted};font-size:.75rem;font-weight:750;letter-spacing:.055em;text-transform:uppercase}}
        .kpi-value{{color:{text_color};font-size:1.48rem;font-weight:800;line-height:1.12;white-space:nowrap}}
        .kpi-detail{{margin-top:10px;color:{muted};font-size:.74rem;line-height:1.35}}
        @media(max-width:1050px){{.kpi-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
      </style>
    </head>
    <body>
      <section class="kpi-grid">{''.join(blocks)}</section>
    </body>
    </html>
    """

    components.html(source, height=154, scrolling=False)


def _js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_charts(
    monthly: list[dict[str, Any]],
    cycles: list[dict[str, Any]],
    sellers: list[dict[str, Any]],
) -> None:
    primary = str(branding["primary_color"])
    secondary = str(branding["secondary_color"])
    accent = str(branding["accent_color"])
    surface = str(branding["surface_color"])
    text_color = str(branding["text_color"])
    muted = str(branding["muted_text_color"])
    border = str(branding["border_color"])

    source = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <script src="https://cdn.amcharts.com/lib/5/index.js"></script>
      <script src="https://cdn.amcharts.com/lib/5/xy.js"></script>
      <script src="https://cdn.amcharts.com/lib/5/percent.js"></script>
      <script src="https://cdn.amcharts.com/lib/5/themes/Animated.js"></script>
      <style>
        *{{box-sizing:border-box}}
        html,body{{margin:0;padding:0;background:transparent;color:{text_color};font-family:Inter,Segoe UI,Arial,sans-serif}}
        .grid{{display:grid;grid-template-columns:1.4fr 1fr;gap:14px}}
        .card{{overflow:hidden;padding:14px;border:1px solid {border};border-radius:16px;background:{surface};box-shadow:0 7px 22px rgba(15,23,42,.06)}}
        .wide{{grid-column:1/-1}}
        .title{{margin:0 0 3px 4px;color:{text_color};font-size:15px;font-weight:800}}
        .sub{{margin:0 0 8px 4px;color:{muted};font-size:11px}}
        #monthly,#cycles{{width:100%;height:320px}}
        #sellers{{width:100%;height:340px}}
      </style>
    </head>
    <body>
      <div class="grid">
        <section class="card">
          <div class="title">Evolu\u00e7\u00e3o mensal</div>
          <div class="sub">Colunas: premia\u00e7\u00e3o | Linha: faturamento | Compet\u00eancia: MM/AAAA</div>
          <div id="monthly"></div>
        </section>
        <section class="card">
          <div class="title">Situa\u00e7\u00e3o dos ciclos</div>
          <div class="sub">Status atual das janelas M1-M3</div>
          <div id="cycles"></div>
        </section>
        <section class="card wide">
          <div class="title">Premia\u00e7\u00e3o por vendedor</div>
          <div class="sub">Total apurado nos filtros atuais</div>
          <div id="sellers"></div>
        </section>
      </div>

      <script>
      const monthlyData={_js(monthly)};
      const cycleData={_js(cycles)};
      const sellerData={_js(sellers)};
      const PRIMARY="{primary}";
      const SECONDARY="{secondary}";
      const ACCENT="{accent}";
      const SURFACE="{surface}";
      const TEXT="{text_color}";
      const MUTED="{muted}";
      const BORDER="{border}";

      am5.ready(function(){{
        function theme(root){{root.setThemes([am5themes_Animated.new(root)]);}}
        function styleAxis(renderer){{
          renderer.labels.template.setAll({{fill:am5.color(TEXT),fontSize:11}});
          renderer.grid.template.setAll({{stroke:am5.color(BORDER),strokeOpacity:.55}});
        }}

        if(monthlyData.length){{
          const root=am5.Root.new("monthly"); theme(root);
          const chart=root.container.children.push(am5xy.XYChart.new(root,{{panX:false,panY:false,wheelX:"none",wheelY:"none"}}));

          const xr=am5xy.AxisRendererX.new(root,{{minGridDistance:62}}); styleAxis(xr);
          xr.labels.template.setAll({{rotation:0,centerX:am5.p100,centerY:am5.p50}});
          const xa=chart.xAxes.push(am5xy.CategoryAxis.new(root,{{categoryField:"label",renderer:xr}}));
          xa.data.setAll(monthlyData);

          const yr1=am5xy.AxisRendererY.new(root,{{}}); styleAxis(yr1);
          const ya=chart.yAxes.push(am5xy.ValueAxis.new(root,{{renderer:yr1}}));
          const yr2=am5xy.AxisRendererY.new(root,{{opposite:true}}); styleAxis(yr2);
          const yb=chart.yAxes.push(am5xy.ValueAxis.new(root,{{renderer:yr2}}));

          const cols=chart.series.push(am5xy.ColumnSeries.new(root,{{
            name:"Reward",xAxis:xa,yAxis:ya,categoryXField:"label",valueYField:"reward",
            fill:am5.color(PRIMARY),stroke:am5.color(PRIMARY),
            tooltip:am5.Tooltip.new(root,{{labelText:"R$ {{valueY.formatNumber('#,###.00')}}"}})
          }}));
          cols.columns.template.setAll({{fill:am5.color(PRIMARY),stroke:am5.color(PRIMARY),cornerRadiusTL:5,cornerRadiusTR:5,maxWidth:34}});
          cols.data.setAll(monthlyData);

          const line=chart.series.push(am5xy.LineSeries.new(root,{{
            name:"Billing",xAxis:xa,yAxis:yb,categoryXField:"label",valueYField:"billing",
            fill:am5.color(SECONDARY),stroke:am5.color(SECONDARY),
            tooltip:am5.Tooltip.new(root,{{labelText:"R$ {{valueY.formatNumber('#,###.00')}}"}})
          }}));
          line.strokes.template.setAll({{stroke:am5.color(SECONDARY),strokeWidth:3}});
          line.bullets.push(function(){{
            return am5.Bullet.new(root,{{sprite:am5.Circle.new(root,{{radius:4,fill:am5.color(ACCENT),stroke:am5.color(SURFACE),strokeWidth:2}})}});
          }});
          line.data.setAll(monthlyData);
          chart.set("cursor",am5xy.XYCursor.new(root,{{behavior:"none"}}));
          cols.appear(700); line.appear(700); chart.appear(700,80);
        }}

        if(cycleData.length){{
          const root=am5.Root.new("cycles"); theme(root);
          const chart=root.container.children.push(am5percent.PieChart.new(root,{{innerRadius:am5.percent(60),layout:root.verticalLayout}}));
          const series=chart.series.push(am5percent.PieSeries.new(root,{{valueField:"value",categoryField:"category",alignLabels:false}}));
          series.get("colors").set("colors",[
            am5.color(PRIMARY),am5.color(SECONDARY),am5.color(ACCENT),am5.color(MUTED),am5.color(BORDER)
          ]);
          series.labels.template.setAll({{text:"{{value}}",fill:am5.color(TEXT),fontSize:12,fontWeight:"600"}});
          series.ticks.template.set("visible",false);
          series.slices.template.setAll({{stroke:am5.color(SURFACE),strokeWidth:2,tooltipText:"{{category}}: {{value}}"}});
          series.data.setAll(cycleData);
          const legend=chart.children.push(am5.Legend.new(root,{{centerX:am5.p50,x:am5.p50,marginTop:8}}));
          legend.labels.template.setAll({{fill:am5.color(TEXT),fontSize:11}});
          legend.valueLabels.template.setAll({{fill:am5.color(MUTED),fontSize:11}});
          legend.data.setAll(series.dataItems);
          series.appear(700,80);
        }}

        if(sellerData.length){{
          const root=am5.Root.new("sellers"); theme(root);
          const chart=root.container.children.push(am5xy.XYChart.new(root,{{panX:false,panY:false,wheelX:"none",wheelY:"none"}}));
          const yr=am5xy.AxisRendererY.new(root,{{inversed:true,minGridDistance:24}}); styleAxis(yr);
          yr.labels.template.setAll({{fontSize:11,maxWidth:220,oversizedBehavior:"truncate"}});
          const ya=chart.yAxes.push(am5xy.CategoryAxis.new(root,{{categoryField:"seller",renderer:yr}})); ya.data.setAll(sellerData);
          const xr=am5xy.AxisRendererX.new(root,{{}}); styleAxis(xr);
          const xa=chart.xAxes.push(am5xy.ValueAxis.new(root,{{min:0,renderer:xr}}));
          const series=chart.series.push(am5xy.ColumnSeries.new(root,{{
            xAxis:xa,yAxis:ya,categoryYField:"seller",valueXField:"value",
            fill:am5.color(ACCENT),stroke:am5.color(ACCENT),
            tooltip:am5.Tooltip.new(root,{{labelText:"{{categoryY}}: R$ {{valueX.formatNumber('#,###.00')}}"}})
          }}));
          series.columns.template.setAll({{fill:am5.color(ACCENT),stroke:am5.color(ACCENT),height:am5.percent(64),cornerRadiusTR:6,cornerRadiusBR:6}});
          series.data.setAll(sellerData);
          series.appear(700); chart.appear(700,80);
        }}
      }});
      </script>
    </body>
    </html>
    """

    components.html(source, height=740, scrolling=False)


from app_core.commission_v4 import (
    build_ledger, period_label, commercial_totals, band, due_items,
    eligible_roster, unit_target,
)
from app_core.shared_identity import get_all_shared_users
from app_core.client_identity import blocked_contract_sellers, documents_by_client, document_for_client, norm as identity_norm
from app_core.commission_policy import first_month_percent, installation_attainment, money
from app_core.simulator_pricing import contract_product_values, get_simulator_pricing, parse_period_key


def _read_items(record: dict) -> list[dict]:
    items = record.get("itens_detalhados") or []
    if isinstance(items,list) and items:
        return [i for i in items if isinstance(i,dict)]
    run_id = record.get("latest_run_id")
    return umdb.get_billing_run_items(str(run_id)) if run_id else []


def _brl(value: float) -> str:
    number = f"{float(value or 0):,.2f}"
    return "R$ " + number.replace(",", "_").replace(".", ",").replace("_", ".")


st.title("Premiação de Vendedores")
try:
    pricing = get_simulator_pricing()
    contracts = {d.id:d.to_dict() for d in db.collection("client_contracts").stream()}
    history = umdb.get_billing_history(limit=20000)
    shared_users = get_all_shared_users()
except Exception as exc:
    st.error(f"Falha ao consultar contratos e faturamento: {exc}")
    st.stop()
if not contracts:
    st.warning("Nenhum contrato cadastrado.")
    st.stop()

blocked_sellers = blocked_contract_sellers(contracts,shared_users)
client_documents = documents_by_client(contracts)
now_month = datetime.now(ZoneInfo("America/Porto_Velho")).strftime("%Y-%m")
try:
    ledger = build_ledger(
        contracts, history, pricing, now_month=now_month,
        parse_billing_period=parse_period_key,
        contract_values=contract_product_values, item_reader=_read_items,
        blocked_sellers=blocked_sellers,
    )
except Exception as exc:
    st.error(f"Não foi possível apurar as comissões: {exc}")
    st.stop()

st.markdown("### Meta comercial e faixas dos vendedores")
months = ledger["months"]
selected_month = st.selectbox("Competência das vendas", months, format_func=period_label, key="meta5_month_v4")
roster = ledger["roster"].get(selected_month,[])
active_count = len(roster)
month_sales = ledger["sales"].get(selected_month,{})
monthly_contract_sales = commercial_totals(contracts, selected_month)
if active_count:
    st.caption(f"Meta individual: 25 ÷ {active_count} vendedor(es) com vendas = {unit_target(active_count):.2f} unidades.")
    performance=[]
    for seller in roster:
        units = int(month_sales.get(seller,0))
        attain = float(installation_attainment(units,active_count))
        sales_value = money(monthly_contract_sales.get(seller,0))
        performance.append({
            "Vendedor":seller,
            "Meta individual (un.)":unit_target(active_count),
            "Unidades vendidas":units,
            "Atingimento (%)":round(attain,2),
            "Taxa M1 estimada (%)":float(first_month_percent(attain)),
            "Contratos vendidos no mês (R$)":sales_value,
            "Faixa comercial":band(sales_value),
        })
    st.dataframe(pd.DataFrame(performance),hide_index=True,use_container_width=True,
        column_config={"Contratos vendidos no mês (R$)":st.column_config.NumberColumn(format="R$ %.2f")})
else:
    st.warning("Nenhum vendedor ativo com venda faturada nesta competência.")
st.caption("Faixa comercial: soma mensal negociada dos contratos elegíveis assinados no período, por vendedor. O bônus recorrente continua calculado pelo faturamento mensal M1–M3, sem somar M4 ou posteriores. Vendas não comprovam instalações.")

st.markdown("### Comissões por ciclo de premiação")
status_view = st.radio("Exibir",["Ciclos em vigência", "Histórico encerrado", "Todos os ciclos"],horizontal=True)
client_frame = pd.DataFrame(ledger["clients"])
frame = pd.DataFrame(ledger["rows"])
if frame.empty or client_frame.empty:
    st.info("Não há contratos com vendedor e competência válidos para apuração.")
    st.stop()
if status_view == "Ciclos em vigência":
    allowed = client_frame[client_frame["Status ciclo"].isin(["AGUARDANDO M1","EM ANDAMENTO","PROGRAMADO"])]
elif status_view == "Histórico encerrado":
    allowed = client_frame[client_frame["Status ciclo"].isin(["ENCERRADO","ENCERRADO SEM M1"])]
else:
    allowed = client_frame
current_pairs = set(zip(allowed["Vendedor"],allowed["Cliente"],allowed["Data contrato"]))
view = frame[[
    (r["Vendedor"],r["Cliente"],r["Data contrato"]) in current_pairs
    for _,r in frame.iterrows()
]].copy()
a,b,c,d = st.columns(4)
active_choices = sorted({name for name in client_frame["Vendedor"].dropna().unique().tolist()
                         if identity_norm(name) not in blocked_sellers},key=str.casefold)
seller_choice = a.selectbox("Vendedor",["Todos"]+active_choices,key="commission_v4_seller")
client_choice = b.selectbox("Cliente",["Todos"]+sorted(client_frame["Cliente"].dropna().unique().tolist()),key="commission_v4_client")
years = sorted({int(p[:4]) for p in frame["Competência"] if p},reverse=True)
year_choice = c.selectbox("Ano",["Todos"]+years,key="commission_v4_year")
month_choice = d.selectbox("Mês",["Todos"]+list(range(1,13)),format_func=lambda v:"Todos" if v=="Todos" else f"{v:02d}",key="commission_v4_filter_month")
view=view[~view["Vendedor"].map(lambda seller: identity_norm(seller) in blocked_sellers)].copy()
if seller_choice!="Todos": view=view[view["Vendedor"]==seller_choice]
if client_choice!="Todos": view=view[view["Cliente"]==client_choice]
if year_choice!="Todos":view=view[view["Competência"].str.startswith(f"{year_choice}-")]
if month_choice!="Todos":view=view[view["Competência"].str.endswith(f"-{month_choice:02d}")]
view=view.copy()
visible_pairs=set(zip(view["Vendedor"],view["Cliente"],view["Data contrato"]))
visible_clients=allowed[[
    (r["Vendedor"],r["Cliente"],r["Data contrato"]) in visible_pairs
    for _,r in allowed.iterrows()
]].copy()

# A situação de pagamento da comissão é consultada em coleção própria.
# A ausência de pagamento registrado NUNCA é interpretada como fatura não recebida.
try:
    payment_docs={d.id:d.to_dict() for d in db.collection("commission_payments").stream()}
except Exception as exc:
    st.error(f"Não foi possível consultar o controle de pagamentos: {exc}")
    st.stop()
from app_core.commission_v4 import commission_id

if not view.empty:
    paid_values=[]
    due_values=[]
    initial_paid=[]
    recurring_paid=[]
    for _,r in view.iterrows():
        paid_m1=0.0;paid_rec=0.0
        if r["Apuração possível"]:
            for component,col in (("M1","Premiação M1 (R$)"),("RECORRENTE","Premiação recorrente (R$)")):
                if money(r[col])<=0:continue
                record=payment_docs.get(commission_id(r["Contrato"],r["Cliente"],r["Competência"],component),{})
                if record.get("status")=="PAGO":
                    if component=="M1":paid_m1=money(record.get("valor_pago",0))
                    else:paid_rec=money(record.get("valor_pago",0))
        total=money(r["Premiação M1 (R$)"]+r["Premiação recorrente (R$)"])
        paid=money(paid_m1+paid_rec)
        initial_paid.append(paid_m1);recurring_paid.append(paid_rec)
        paid_values.append(paid)
        due_values.append(max(0,money(total-paid)))
    view["Comissão paga (R$)"]=paid_values
    view["Saldo em aberto (R$)"]=due_values
    view["M1 já paga (R$)"]=initial_paid
    view["Recorrência já paga (R$)"]=recurring_paid
else:
    for col in ("Comissão paga (R$)","Saldo em aberto (R$)","M1 já paga (R$)","Recorrência já paga (R$)"):
        view[col]=pd.Series(dtype=float)

first=money(view["Premiação M1 (R$)"].sum())
recurring=money(view["Premiação recorrente (R$)"].sum())
paid=money(view["Comissão paga (R$)"].sum())
billed=money(view["Valor faturado (R$)"].sum())
render_kpis([
    {"label":"Comissão apurada","value":_brl(first+recurring),"detail":"Somente competências M1, M2 e M3","accent":"#2563eb"},
    {"label":"Premiação M1","value":_brl(first),"detail":"Taxa por atingimento da meta","accent":"#0f766e"},
    {"label":"Bônus recorrente","value":_brl(recurring),"detail":"Faixas Prata / Ouro / Diamante","accent":"#7c3aed"},
    {"label":"Comissões pagas","value":_brl(paid),"detail":"Registradas no controle financeiro","accent":"#475569"},
    {"label":"Saldo em aberto","value":_brl(view["Saldo em aberto (R$)"].sum()),"detail":"Não equivale a valor já liberado","accent":"#dc2626"},
])
st.page_link("pages/9_Controle_Pagamentos_Comissoes.py", label="Abrir controle de pagamentos de comissão")

st.markdown("### Consolidado por vendedor")
if view.empty:
    grouped=pd.DataFrame(columns=["Vendedor","Faturamento (R$)","Premiação M1 (R$)","Premiação recorrente (R$)","Total apurado (R$)","Comissão paga (R$)","Saldo em aberto (R$)"])
else:
    grouped=view.groupby("Vendedor",as_index=False)[
        ["Valor faturado (R$)","Premiação M1 (R$)","Premiação recorrente (R$)","Comissão paga (R$)","Saldo em aberto (R$)"]
    ].sum().rename(columns={"Valor faturado (R$)":"Faturamento (R$)"})
    grouped["Total apurado (R$)"]=grouped["Premiação M1 (R$)"]+grouped["Premiação recorrente (R$)"]
    chosen_commercial_month = monthly_contract_sales if selected_month else {}
    grouped["Contratos vendidos no período selecionado (R$)"]=[money(chosen_commercial_month.get(s,0)) for s in grouped["Vendedor"]]
    grouped["Faixa comercial"]=[band(v) for v in grouped["Contratos vendidos no período selecionado (R$)"]]
    # A faixa recorrente é por competência, e não pela soma da janela M1-M3.
    groups_month=view[view["Apuração possível"]].groupby(["Vendedor","Competência"],as_index=False)["Valor faturado (R$)"].sum()
    last_bands={}
    for _,r in groups_month.iterrows():
        seller=r["Vendedor"];per=r["Competência"]
        if seller not in last_bands or per>last_bands[seller][0]:
            last_bands[seller]=(per,band(r["Valor faturado (R$)"]))
    grouped["Faixa recorrente (última competência)"]=[last_bands.get(s,("","Sem bônus"))[1] for s in grouped["Vendedor"]]
st.dataframe(grouped,hide_index=True,use_container_width=True)

st.markdown("### Evolução mensal — competência das faturas (MM/AAAA)")
monthly_data={}
for _,r in view.iterrows():
    period=str(r["Competência"] or "")
    if not period or not r["Apuração possível"]:continue
    values=monthly_data.setdefault(period,{"billing":0.0,"reward":0.0})
    values["billing"]+=float(r["Valor faturado (R$)"])
    values["reward"]+=float(r["Premiação M1 (R$)" ]+r["Premiação recorrente (R$)"])
month_chart=[{"period":p,"label":f"{p[5:7]}/{p[:4]}","billing":v["billing"],"reward":v["reward"]} for p,v in sorted(monthly_data.items())]
cycle_chart=[{"category":str(k),"value":int(v)} for k,v in visible_clients["Status ciclo"].value_counts().items()] if not visible_clients.empty else []
seller_chart=[{"seller":str(r["Vendedor"]),"value":float(r["Total apurado (R$)"])} for _,r in grouped.sort_values("Total apurado (R$)",ascending=False).head(12).iterrows()] if not grouped.empty else []
render_charts(month_chart,cycle_chart,seller_chart)
if not month_chart:st.caption("Sem competência faturada elegível para os filtros selecionados.")

st.markdown("### Detalhamento da premiação")
t1,t2,t3,t4=st.tabs(["Etapa 1 — M1","Contratos no ciclo","Recorrência M1–M3","Pendências e auditoria"])
with t1:
    st.dataframe(view[view["Fatura"]=="M1"],hide_index=True,use_container_width=True)
with t2:
    st.dataframe(visible_clients,hide_index=True,use_container_width=True)
with t3:
    st.dataframe(view,hide_index=True,use_container_width=True)
with t4:
    st.dataframe(view[view["Status"].str.contains("PENDENTE|SEM FATURAMENTO|INELEGÍVEL|FORA",case=False,na=False)],hide_index=True,use_container_width=True)
    st.caption("Histórico encerrado permanece consultável. Registrar pagamento de comissão é diferente de confirmar o recebimento da fatura.")

# Acrescenta documento sem inserir valores artificiais: a origem é client_contracts.
# O consolidado por cliente inclui CPF/CNPJ, preservado como TEXTO no Excel.
if not visible_clients.empty:
    visible_clients = visible_clients.copy()
    visible_clients.insert(2,"CPF/CNPJ",visible_clients["Cliente"].map(
        lambda client: document_for_client(client,client_documents)))
if not view.empty:
    view = view.copy()
    view.insert(2,"CPF/CNPJ",view["Cliente"].map(
        lambda client: document_for_client(client,client_documents)))
output=io.BytesIO()
with pd.ExcelWriter(output,engine="openpyxl") as writer:
    grouped.to_excel(writer,index=False,sheet_name="Por vendedor")
    visible_clients.to_excel(writer,index=False,sheet_name="Por cliente")
    view.to_excel(writer,index=False,sheet_name="M1-M3")
    for worksheet in writer.book.worksheets:
        for cell in worksheet[1]:
            if cell.value=="CPF/CNPJ":
                col=cell.column
                for row in worksheet.iter_rows(min_row=2,min_col=col,max_col=col):
                    row[0].number_format="@"
st.download_button("Baixar apuração em Excel",data=output.getvalue(),file_name="comissoes_meta5_v4.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)

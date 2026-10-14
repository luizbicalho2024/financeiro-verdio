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
          <div class="sub">Faturamento M1-M3 x premia\u00e7\u00e3o apurada</div>
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

          const xr=am5xy.AxisRendererX.new(root,{{minGridDistance:45}}); styleAxis(xr);
          xr.labels.template.setAll({{rotation:-35,centerX:am5.p100,centerY:am5.p50}});
          const xa=chart.xAxes.push(am5xy.CategoryAxis.new(root,{{categoryField:"period",renderer:xr}}));
          xa.data.setAll(monthlyData);

          const yr1=am5xy.AxisRendererY.new(root,{{}}); styleAxis(yr1);
          const ya=chart.yAxes.push(am5xy.ValueAxis.new(root,{{renderer:yr1}}));
          const yr2=am5xy.AxisRendererY.new(root,{{opposite:true}}); styleAxis(yr2);
          const yb=chart.yAxes.push(am5xy.ValueAxis.new(root,{{renderer:yr2}}));

          const cols=chart.series.push(am5xy.ColumnSeries.new(root,{{
            name:"Reward",xAxis:xa,yAxis:ya,categoryXField:"period",valueYField:"reward",
            fill:am5.color(PRIMARY),stroke:am5.color(PRIMARY),
            tooltip:am5.Tooltip.new(root,{{labelText:"R$ {{valueY.formatNumber('#,###.00')}}"}})
          }}));
          cols.columns.template.setAll({{fill:am5.color(PRIMARY),stroke:am5.color(PRIMARY),cornerRadiusTL:5,cornerRadiusTR:5,maxWidth:34}});
          cols.data.setAll(monthlyData);

          const line=chart.series.push(am5xy.LineSeries.new(root,{{
            name:"Billing",xAxis:xa,yAxis:yb,categoryXField:"period",valueYField:"billing",
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


from app_core.commission_auto import sold_units_by_seller, payment_confirmed, activity_confirmed
from app_core.commission_policy import (
    contract_discount, discount_is_eligible, first_month_percent,
    installation_attainment, money, percent_reward,
    recurring_percent, shift_month, target_for_seller,
)
from app_core.simulator_pricing import (
    contract_product_values, get_simulator_pricing, parse_period_key,
)
import hashlib
import unicodedata


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def _brl(value: float) -> str:
    s = f"{float(value or 0):,.2f}"
    return "R$ " + s.replace(",", "_").replace(".", ",").replace("_", ".")


def _get_doc(collection: str, document: str) -> dict:
    snapshot = db.collection(collection).document(document).get()
    return (snapshot.to_dict() or {}) if snapshot.exists else {}


def _read_items(record: dict | None) -> list[dict]:
    if not record:
        return []
    items = record.get("itens_detalhados")
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]
    run_id = record.get("latest_run_id")
    return umdb.get_billing_run_items(str(run_id)) if run_id else []


def _value(item: dict, *names: str) -> float:
    for name in names:
        if name in item and item[name] not in (None, ""):
            try:
                value = str(item[name]).replace("R$", "").strip()
                if "," in value and "." in value:
                    value = value.replace(".", "").replace(",", ".")
                elif "," in value:
                    value = value.replace(",", ".")
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def _billed(record: dict | None) -> float:
    if not record:
        return 0.0
    if record.get("valor_total") not in (None, ""):
        return max(0.0, _value(record, "valor_total"))
    return max(0.0, sum(
        _value(item, "Valor a Faturar", "valor_faturado", "valor_a_faturar")
        for item in _read_items(record)
        if _norm(item.get("Categoria") or item.get("categoria")) != "suspenso"
    ))


def _parse_month(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m")
    text = str(value or "")
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return ""


def _key(doc_id: str, client: str, period: str) -> str:
    return hashlib.sha256(f"{doc_id}|{_norm(client)}|{period}".encode()).hexdigest()[:24]


st.title("Premiação de Vendedores — Política Meta 5 Verdio")
st.caption("Bionio Frotas | Premiação não recorrente (M1) + bônus recorrente por faturamento M1–M3")

try:
    pricing = get_simulator_pricing()
    contracts = {
        document.id: document.to_dict()
        for document in db.collection("client_contracts").stream()
    }
    history = umdb.get_billing_history(limit=20000)
except Exception as exc:
    st.error(f"Falha ao consultar os dados de origem: {exc}")
    st.stop()

if not contracts:
    st.warning("Cadastre primeiro os contratos na página Contratos e Preços por Cliente.")
    st.stop()

sellers = sorted({str(c.get("vendedor") or "").strip() for c in contracts.values() if str(c.get("vendedor") or "").strip()})
if not sellers:
    st.warning("Nenhum contrato possui vendedor identificado.")
    st.stop()

# Histórico retorna snapshots vigentes por cliente e competência; nunca soma revisões.
history_index: dict[tuple[str, str], dict] = {}
for entry in history:
    period = parse_period_key(entry)
    client_id = _norm(entry.get("cliente"))
    if period and client_id:
        history_index.setdefault((client_id, period), entry)

months_in_history = sorted({period for _, period in history_index})
now_month = datetime.now(ZoneInfo("America/Porto_Velho")).strftime("%Y-%m")

# Volume de vendas atribuido no cadastro de contratos, somente com
# faturamento positivo no historico. NAO equivale a instalacoes confirmadas.
billed_months_by_client: dict[str, set[str]] = {}
for (client, period), item in history_index.items():
    if _billed(item) > 0 and period <= now_month:
        billed_months_by_client.setdefault(client, set()).add(period)
sales_by_month = sold_units_by_seller(contracts, billed_months_by_client)
all_months = sorted(set(months_in_history) | set(sales_by_month) | {now_month}, reverse=True)

st.markdown("### 1. Meta comercial automática — vendas atribuídas")
selected_month = st.selectbox("Competência comercial", all_months, key="meta_period")
month_sales = sales_by_month.get(selected_month, {})
active_sellers_count = len(month_sales)
if not month_sales:
    st.caption("Não há contratos com unidades vendidas e faturamento registrado nesta competência.")
else:
    seller_target = target_for_seller(active_sellers_count)
    sales_rows = []
    for seller_name, units in sorted(month_sales.items()):
        attained = float(installation_attainment(int(units), active_sellers_count))
        sales_rows.append({
            "Vendedor": seller_name,
            "Unidades vendidas (contratos faturados)": int(units),
            "Meta individual (un.)": float(seller_target),
            "Atingimento de vendas (%)": round(attained, 2),
            "Taxa inicial estimada (%)": float(first_month_percent(attained)),
        })
    st.caption(f"{active_sellers_count} vendedor(es) com vendas faturadas em {selected_month}. Meta dividida automaticamente: 25 ÷ {active_sellers_count}.")
    st.dataframe(pd.DataFrame(sales_rows), hide_index=True, use_container_width=True)


# Os tres meses começam no primeiro faturamento positivo do contrato.
# Precalcula períodos positivos evitando percorrer todo o historico por contrato.
positive_periods: dict[str, list[str]] = {}
for (client_name, invoice_month), entry in history_index.items():
    if _billed(entry) > 0:
        positive_periods.setdefault(client_name, []).append(invoice_month)
for months in positive_periods.values():
    months.sort()
# Nao se presume pagamento nem atividade a partir da simples emissão.
records: list[dict] = []
clients: list[dict] = []
missing_seller: list[str] = []
for doc_id, contract in contracts.items():
    client = str(contract.get("cliente") or doc_id).strip()
    seller = str(contract.get("vendedor") or "").strip()
    if not seller:
        missing_seller.append(client)
        continue
    signed = _parse_month(contract.get("ultima_atualizacao_termo"))
    if not signed:
        continue
    prices, quantities = contract_product_values(contract, pricing)
    table_snapshot = contract.get("precos_tabela_produtos") or {}
    discount, discount_reason = contract_discount(prices, quantities, table_snapshot)
    eligible = discount_is_eligible(discount)
    client_periods = [
        period for period in positive_periods.get(_norm(client), [])
        if period >= signed
    ]
    first_period = client_periods[0] if client_periods else None
    # Apuracao automatica pelo mes da assinatura e unidades vendidas.
    # A fonte nao possui eventos de instalacao por dispositivo/vendedor.
    sale_month = signed
    month_sales = sales_by_month.get(sale_month, {})
    number_sellers = len(month_sales)
    target_ready = number_sellers > 0 and seller in month_sales
    count = int(month_sales.get(seller, 0)) if target_ready else 0
    attainment = float(installation_attainment(count, number_sellers)) if target_ready else None
    m1_percent = float(first_month_percent(attainment)) if attainment is not None else 0.0


    row_indices = []
    for idx in range(3):
        period = shift_month(first_period, idx) if first_period else ""
        invoice = history_index.get((_norm(client), period)) if period else None
        billing = money(_billed(invoice))
        # Historico do faturamento ja seleciona a competencia automaticamente.
        # Dados de liquidação/atividade só valem se houver campos explícitos.
        payment = payment_confirmed(invoice, billing)
        activity = activity_confirmed(invoice)
        expiration = _parse_month(contract.get("vencimento_contrato"))
        in_contract_term = not expiration or period <= expiration
        preliminary = bool(
            eligible and invoice and billing > 0 and in_contract_term
            and period <= now_month
        )
        # Para a premiacao M1, venda cadastrada ainda nao comprova
        # instalacao. Exige uma origem operacional explicita se disponivel.
        installation_proof = contract.get("instalacoes_confirmadas") is True
        payable = bool(preliminary and payment is True and activity is True
                       and (idx != 0 or installation_proof))
        if not eligible:
            status = "NÃO ELEGÍVEL — DESCONTO/TABELA"
        elif not first_period:
            status = "AGUARDANDO PRIMEIRO FATURAMENTO"
        elif not invoice or billing <= 0:
            status = "SEM FATURAMENTO"
        elif period > now_month:
            status = "COMPETÊNCIA FUTURA"
        elif not in_contract_term:
            status = "CONTRATO FORA DA VIGÊNCIA"
        elif payable:
            status = "LIBERÁVEL — RECEBIMENTO E ATIVIDADE CONFIRMADOS"
        elif preliminary and payment is True and activity is True and idx == 0:
            status = "PROJEÇÃO — INSTALAÇÕES NÃO CONFIRMADAS"
        else:
            status = "PROJEÇÃO — AGUARDANDO DADOS DE RECEBIMENTO/ATIVIDADE"


        row = {
            "Vendedor": seller, "Cliente": client, "Contrato": doc_id,
            "Data contrato": signed, "Competência da venda": sale_month,
            "Fatura": f"M{idx+1}", "Competência": period,
            "Fim da janela": shift_month(first_period, 2) if first_period else "",
            "Desconto (%)": discount, "Referência": discount_reason,
            "Elegível": eligible, "Meta (%)": attainment,
            "Unidades vendidas pelo vendedor": count if target_ready else None,
            "Meta calculada": target_ready,
            "Valor faturado (R$)": billing,
            "Pagamento": "CONFIRMADO" if payment is True else ("NÃO RECEBIDO" if payment is False else "SEM INFORMAÇÃO"),
            "Atividade": "CONFIRMADA" if activity is True else ("INATIVA" if activity is False else "SEM INFORMAÇÃO"),
            "Contrato vigente": in_contract_term,
            "Instalação comprovada": installation_proof,
            "Status": status, "Apuração possível": preliminary, "Apto a pagar": payable,
            "Taxa M1 (%)": m1_percent if target_ready else 0.0,
            "Bônus recorrente (%)": 0.0,
            "Premiação M1 (R$)": 0.0, "Premiação recorrente (R$)": 0.0,
            "Premiação liberável (R$)": 0.0,
        }
        row_indices.append(len(records))
        records.append(row)
    clients.append({
        "Vendedor": seller, "Cliente": client, "Data contrato": signed,
        "Competência da venda": sale_month,
        "M1": first_period or "PENDENTE",
        "M2": shift_month(first_period, 1) if first_period else "",
        "M3": shift_month(first_period, 2) if first_period else "",
        "Desconto (%)": discount,
        "Elegibilidade": "ELEGÍVEL" if eligible else "NÃO ELEGÍVEL",
        "Justificativa": discount_reason if discount is None else (
            "Desconto acima de 15%" if not eligible else "Desconto dentro do limite"
        ),
        "Meta (%)": attainment,
        "Premiação M1 (R$)": 0.0,
        "Premiação recorrente (R$)": 0.0,
        "Total apurado (R$)": 0.0,
        "Total liberável (R$)": 0.0,
        "indices": row_indices,
    })

# A faixa recorrente projetada usa apenas valores FATURADOS elegíveis de M1-M3.
# O status liberavel depende de provas financeiras e operacionais de origem.
monthly_totals: dict[tuple[str, str], float] = {}
for row in records:
    if row["Apuração possível"]:
        pair = (row["Vendedor"], row["Competência"])
        monthly_totals[pair] = monthly_totals.get(pair, 0.0) + row["Valor faturado (R$)"]
for row in records:
    if not row["Apuração possível"]:
        continue
    month_total = monthly_totals[(row["Vendedor"], row["Competência"])]
    pct = float(recurring_percent(month_total))
    row["Bônus recorrente (%)"] = pct
    row["Premiação recorrente (R$)"] = percent_reward(row["Valor faturado (R$)"], pct)
    if row["Fatura"] == "M1" and row["Meta calculada"]:
        row["Premiação M1 (R$)"] = percent_reward(row["Valor faturado (R$)"], row["Taxa M1 (%)"])
    if row["Apto a pagar"]:
        row["Premiação liberável (R$)"] = money(row["Premiação M1 (R$)"] + row["Premiação recorrente (R$)"])

for client in clients:
    related = [records[i] for i in client.pop("indices")]
    client["Premiação M1 (R$)"] = money(sum(r["Premiação M1 (R$)"] for r in related))
    client["Premiação recorrente (R$)"] = money(sum(r["Premiação recorrente (R$)"] for r in related))
    client["Total apurado (R$)"] = money(client["Premiação M1 (R$)"] + client["Premiação recorrente (R$)"])
    client["Total liberável (R$)"] = money(sum(r["Premiação liberável (R$)"] for r in related))
    end = related[-1]["Competência"]
    client["Status ciclo"] = (
        "AGUARDANDO M1" if not end else
        "ENCERRADO" if end < now_month else
        "EM ANDAMENTO" if related[0]["Competência"] <= now_month else
        "PROGRAMADO"
    )

if missing_seller:
    st.warning(f"{len(missing_seller)} contrato(s) sem vendedor foram desconsiderados: " + ", ".join(missing_seller[:10]))
if not records:
    st.info("Não há contratos com período e vendedor válidos para apuração.")
    st.stop()

frame = pd.DataFrame(records)
client_frame = pd.DataFrame(clients)



st.markdown("### Apuração e indicadores")
a, b, c, d = st.columns(4)
chosen_seller = a.selectbox("Vendedor", ["Todos"] + sellers)
chosen_client = b.selectbox("Cliente", ["Todos"] + sorted(client_frame["Cliente"].unique().tolist()))
chosen_year = c.selectbox("Ano", ["Todos"] + sorted({int(p[:4]) for p in frame["Competência"] if p}, reverse=True))
chosen_month = d.selectbox("Mês", ["Todos"] + list(range(1, 13)), format_func=lambda x: "Todos" if x == "Todos" else f"{x:02d}")

view = frame.copy()
if chosen_seller != "Todos":
    view = view[view["Vendedor"] == chosen_seller]
if chosen_client != "Todos":
    view = view[view["Cliente"] == chosen_client]
if chosen_year != "Todos":
    view = view[view["Competência"].str.startswith(f"{chosen_year}-")]
if chosen_month != "Todos":
    view = view[view["Competência"].str.endswith(f"-{int(chosen_month):02d}")]

pairs = set(zip(view["Vendedor"], view["Cliente"]))
visible_clients = client_frame[[
    (row["Vendedor"], row["Cliente"]) in pairs
    for _, row in client_frame.iterrows()
]].copy()
if chosen_year != "Todos" or chosen_month != "Todos":
    results = view.groupby(["Vendedor", "Cliente"], as_index=False)[
        ["Premiação M1 (R$)", "Premiação recorrente (R$)", "Premiação liberável (R$)"]
    ].sum().rename(columns={"Premiação liberável (R$)": "Total liberável (R$)"})
    if not visible_clients.empty:
        visible_clients = visible_clients.drop(columns=["Premiação M1 (R$)", "Premiação recorrente (R$)", "Total apurado (R$)", "Total liberável (R$)"])
        visible_clients = visible_clients.merge(results, on=["Vendedor", "Cliente"], how="left")
        visible_clients["Total apurado (R$)"] = visible_clients["Premiação M1 (R$)"] + visible_clients["Premiação recorrente (R$)"]

total_first = money(view["Premiação M1 (R$)"].sum())
total_recurring = money(view["Premiação recorrente (R$)"].sum())
total_billed = money(view["Valor faturado (R$)"].sum())
pending = int(view["Status"].str.startswith("PROJEÇÃO").sum())
releasable = money(view["Premiação liberável (R$)"].sum())
render_kpis([
    {"label": "Comissão prevista", "value": _brl(total_first+total_recurring), "detail": "M1 + recorrência sobre faturamento", "accent": "#2563eb"},
    {"label": "Premiação não recorrente", "value": _brl(total_first), "detail": "10%, 15% ou 20% de M1", "accent": "#0f766e"},
    {"label": "Bônus recorrente", "value": _brl(total_recurring), "detail": "Faixa 0% / 2% / 3% / 4%", "accent": "#7c3aed"},
    {"label": "Faturamento exibido", "value": _brl(total_billed), "detail": "Inclui pendências", "accent": "#475569"},
    {"label": "Liberável com evidências", "value": _brl(releasable), "detail": f"{pending} competência(s) ainda projetadas", "accent": "#dc2626"},
])

st.markdown("### Consolidado por vendedor")
if view.empty:
    grouped = pd.DataFrame(columns=["Vendedor", "Faturamento (R$)", "Premiação M1 (R$)", "Premiação recorrente (R$)", "Total apurado (R$)", "Total liberável (R$)"])
else:
    grouped = view.groupby("Vendedor", as_index=False).agg({
        "Valor faturado (R$)": "sum", "Premiação M1 (R$)": "sum", "Premiação recorrente (R$)": "sum", "Premiação liberável (R$)": "sum",
    }).rename(columns={"Valor faturado (R$)": "Faturamento (R$)"})
    grouped["Total apurado (R$)"] = grouped["Premiação M1 (R$)"] + grouped["Premiação recorrente (R$)"]
    grouped = grouped.rename(columns={"Premiação liberável (R$)": "Total liberável (R$)"})
st.dataframe(grouped, hide_index=True, use_container_width=True)

monthly = {}
for _, r in view.iterrows():
    period = str(r["Competência"])
    if not period:
        continue
    values = monthly.setdefault(period, {"billing": 0.0, "reward": 0.0})
    values["billing"] += float(r["Valor faturado (R$)"])
    values["reward"] += float(r["Premiação M1 (R$)"] + r["Premiação recorrente (R$)"])
month_chart = [{"period": period, **data} for period, data in sorted(monthly.items())]
cycle_chart = [{"category": str(k), "value": int(v)} for k, v in visible_clients["Status ciclo"].value_counts().items()] if not visible_clients.empty else []
seller_chart = [{"seller": str(r["Vendedor"]), "value": float(r["Total apurado (R$)"])} for _, r in grouped.sort_values("Total apurado (R$)", ascending=False).head(12).iterrows()] if not grouped.empty else []
render_charts(month_chart, cycle_chart, seller_chart)

first_tab, client_tab, recurring_tab, checks_tab = st.tabs([
    "Etapa 1 — Premiação M1", "Consolidado por cliente", "Etapa 2 — Recorrência M1–M3", "Pendências e auditoria"
])
with first_tab:
    st.dataframe(view[view["Fatura"] == "M1"].drop(columns=["Contrato"], errors="ignore"), hide_index=True, use_container_width=True)
with client_tab:
    st.dataframe(visible_clients, hide_index=True, use_container_width=True)
with recurring_tab:
    st.dataframe(view.drop(columns=["Contrato"], errors="ignore"), hide_index=True, use_container_width=True)
with checks_tab:
    problem = view[view["Status"] != "APURADA"]
    st.dataframe(problem.drop(columns=["Contrato"], errors="ignore"), hide_index=True, use_container_width=True)
    st.caption("Comissão prevista não é comprovante de pagamento. Apenas competências com dados explícitos de recebimento e atividade ficam liberáveis.")

output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    grouped.to_excel(writer, index=False, sheet_name="Por Vendedor")
    visible_clients.to_excel(writer, index=False, sheet_name="Por Cliente")
    view.drop(columns=["Contrato"], errors="ignore").to_excel(writer, index=False, sheet_name="Faturas M1-M3")
st.download_button(
    "Baixar apuração em Excel", data=output.getvalue(),
    file_name="comissoes_meta5_verdio.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
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
st.info(
    "**Condições:** contrato B2B com desconto de até 15% sobre a tabela oficial; "
    "instalações comprovadas para a meta; faturamento emitido, recebido e dispositivos ativos. "
    "Faturas sem comprovação não são consideradas como valor a pagar."
)

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
install_months = [
    str(c.get("competencia_instalacao") or "")
    for c in contracts.values()
    if len(str(c.get("competencia_instalacao") or "")) == 7
]
all_months = sorted(set(months_in_history + install_months + [now_month]), reverse=True)

# Aprovações ficam separadas por competência, evitando um documento único gigantesco.
month_cache: dict[str, dict] = {}
approvals_cache: dict[str, dict] = {}


def target_data(period: str) -> dict:
    if period not in month_cache:
        month_cache[period] = _get_doc("settings", f"commission_attainment_{period}")
    return month_cache[period]


def receipt_data(period: str) -> dict:
    if period not in approvals_cache:
        approvals_cache[period] = _get_doc("settings", f"commission_receipts_{period}")
    return approvals_cache[period]


with st.expander("1. Apuração da meta de instalações por vendedor", expanded=True):
    c1, c2 = st.columns([1, 3])
    selected_month = c1.selectbox("Competência da meta", all_months, key="meta_period")
    current_target = target_data(selected_month)
    active_count = c1.number_input(
        "Vendedores atuantes no mês", min_value=0, max_value=999,
        value=int(current_target.get("active_sellers") or 0), step=1,
        help="Quantidade efetiva publicada para o mês de apuração."
    )
    entries = current_target.get("installed_by_seller") or {}
    editor_source = pd.DataFrame([
        {"Vendedor": name, "Instalações comprovadas": int(entries.get(name, 0) or 0)}
        for name in sellers
    ])
    with c2:
        st.caption("Registre as instalações reais do período, e não a quantidade contratada ou faturada.")
        edited_target = st.data_editor(
            editor_source, hide_index=True, use_container_width=True, num_rows="fixed",
            column_config={
                "Vendedor": st.column_config.TextColumn(disabled=True),
                "Instalações comprovadas": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
            }, key=f"install_editor_{selected_month}",
        )
    if active_count > 0:
        st.metric("Meta individual de dispositivos", f"{float(target_for_seller(int(active_count))):.2f}")
    else:
        st.warning("Informe o total de vendedores atuantes; até lá, M1 não poderá gerar premiação.")
    if st.button("Salvar meta e instalações do mês", type="primary", key="save_attainment"):
        try:
            counted = {
                str(row["Vendedor"]): int(row["Instalações comprovadas"])
                for _, row in edited_target.iterrows()
            }
            if any(qty < 0 for qty in counted.values()):
                raise ValueError("Instalações não podem ser negativas.")
            if active_count < 1:
                raise ValueError("Informe pelo menos um vendedor atuante.")
            db.collection("settings").document(f"commission_attainment_{selected_month}").set({
                "active_sellers": int(active_count),
                "installed_by_seller": counted,
                "updated_at": datetime.now(ZoneInfo("America/Porto_Velho")).isoformat(),
            }, merge=True)
        except Exception as exc:
            st.error(f"Não foi possível salvar a apuração: {exc}")
        else:
            st.success("Meta e instalações gravadas.")
            st.rerun()

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
    # A competência de instalação requer registro próprio, nunca inferência da data do contrato.
    installation_month = str(contract.get("competencia_instalacao") or "").strip()
    target = target_data(installation_month) if installation_month else {}
    number_sellers = int(target.get("active_sellers") or 0)
    installed_by_seller = target.get("installed_by_seller") or {}
    target_ready = number_sellers > 0 and seller in installed_by_seller
    count = int(installed_by_seller.get(seller, 0) or 0) if target_ready else 0
    attainment = float(installation_attainment(count, number_sellers)) if target_ready else None
    m1_percent = float(first_month_percent(attainment)) if attainment is not None else 0.0

    row_indices = []
    for idx in range(3):
        period = shift_month(first_period, idx) if first_period else ""
        invoice = history_index.get((_norm(client), period)) if period else None
        billing = money(_billed(invoice))
        approval_id = _key(doc_id, client, period) if period else ""
        approvals = receipt_data(period).get("rows", {}) if period else {}
        confirmation = approvals.get(approval_id, {})
        receipt_ok = bool(confirmation.get("recebido"))
        active_ok = bool(confirmation.get("ativo"))
        contract_ok = bool(confirmation.get("contrato_ativo"))
        expiration = _parse_month(contract.get("vencimento_contrato"))
        in_contract_term = not expiration or period <= expiration
        final = bool(eligible and invoice and billing > 0 and receipt_ok and active_ok
                     and contract_ok and in_contract_term and period <= now_month)
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
        elif not receipt_ok or not active_ok or not contract_ok:
            status = "PENDENTE COMPROVAÇÃO"
        else:
            status = "APURADA"
        row = {
            "ID": approval_id,
            "Vendedor": seller, "Cliente": client, "Contrato": doc_id,
            "Data contrato": signed, "Competência instalação": installation_month,
            "Fatura": f"M{idx+1}", "Competência": period,
            "Fim da janela": shift_month(first_period, 2) if first_period else "",
            "Desconto (%)": discount, "Referência": discount_reason,
            "Elegível": eligible, "Meta (%)": attainment,
            "Dispositivos instalados": count if target_ready else None,
            "Meta comprovada": target_ready,
            "Valor faturado (R$)": billing,
            "Recebido": receipt_ok, "Dispositivos ativos": active_ok,
            "Contrato ativo": contract_ok,
            "Status": status, "Apto a pagar": final,
            "Taxa M1 (%)": m1_percent if target_ready else 0.0,
            "Bônus recorrente (%)": 0.0,
            "Premiação M1 (R$)": 0.0, "Premiação recorrente (R$)": 0.0,
        }
        row_indices.append(len(records))
        records.append(row)
    clients.append({
        "Vendedor": seller, "Cliente": client, "Data contrato": signed,
        "Instalação": installation_month or "NÃO INFORMADA",
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
        "indices": row_indices,
    })

# A faixa de 2%, 3% ou 4% é calculada sobre o total recebido de cada
# vendedor na competência, considerando SOMENTE contratos dentro de M1-M3.
monthly_totals: dict[tuple[str, str], float] = {}
for row in records:
    if row["Apto a pagar"]:
        pair = (row["Vendedor"], row["Competência"])
        monthly_totals[pair] = monthly_totals.get(pair, 0.0) + row["Valor faturado (R$)"]
for row in records:
    if not row["Apto a pagar"]:
        continue
    month_total = monthly_totals[(row["Vendedor"], row["Competência"])]
    pct = float(recurring_percent(month_total))
    row["Bônus recorrente (%)"] = pct
    row["Premiação recorrente (R$)"] = percent_reward(row["Valor faturado (R$)"], pct)
    if row["Fatura"] == "M1" and row["Meta comprovada"]:
        row["Premiação M1 (R$)"] = percent_reward(row["Valor faturado (R$)"], row["Taxa M1 (%)"])

for client in clients:
    related = [records[i] for i in client.pop("indices")]
    client["Premiação M1 (R$)"] = money(sum(r["Premiação M1 (R$)"] for r in related))
    client["Premiação recorrente (R$)"] = money(sum(r["Premiação recorrente (R$)"] for r in related))
    client["Total apurado (R$)"] = money(client["Premiação M1 (R$)"] + client["Premiação recorrente (R$)"])
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

with st.expander("2. Confirmar recebimento e dispositivos ativos nas faturas", expanded=False):
    st.caption(
        "A confirmação deve refletir a conciliação financeira e a situação operacional reais. "
        "O histórico de faturamento, isoladamente, não comprova pagamento."
    )
    choices = sorted({row["Competência"] for row in records if row["Competência"]}, reverse=True)
    check_month = st.selectbox("Competência a conferir", choices or [now_month], key="receipt_month")
    current = frame[(frame["Competência"] == check_month) & (frame["Valor faturado (R$)"] > 0)].copy()
    if current.empty:
        st.info("Nenhuma fatura positiva nesta competência.")
    else:
        columns = ["ID", "Vendedor", "Cliente", "Fatura", "Valor faturado (R$)", "Recebido", "Dispositivos ativos", "Contrato ativo"]
        edited = st.data_editor(
            current[columns], hide_index=True, use_container_width=True,
            num_rows="fixed", key=f"receipt_editor_{check_month}",
            column_config={
                "ID": st.column_config.TextColumn(disabled=True),
                "Vendedor": st.column_config.TextColumn(disabled=True),
                "Cliente": st.column_config.TextColumn(disabled=True),
                "Fatura": st.column_config.TextColumn(disabled=True),
                "Valor faturado (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
                "Recebido": st.column_config.CheckboxColumn(),
                "Dispositivos ativos": st.column_config.CheckboxColumn(),
                "Contrato ativo": st.column_config.CheckboxColumn(),
            }
        )
        if st.button("Gravar conferência financeira e operacional", type="primary"):
            try:
                approval = receipt_data(check_month)
                rows = dict(approval.get("rows") or {})
                for _, item in edited.iterrows():
                    rows[str(item["ID"])] = {
                        "recebido": bool(item["Recebido"]),
                        "ativo": bool(item["Dispositivos ativos"]),
                        "contrato_ativo": bool(item["Contrato ativo"]),
                        "conferido_por": str(st.session_state.get("user_info", {}).get("email") or "operador"),
                        "conferido_em": datetime.now(ZoneInfo("America/Porto_Velho")).isoformat(),
                    }
                db.collection("settings").document(f"commission_receipts_{check_month}").set({
                    "rows": rows,
                    "updated_at": datetime.now(ZoneInfo("America/Porto_Velho")).isoformat(),
                }, merge=True)
            except Exception as exc:
                st.error(f"Falha ao salvar a conferência: {exc}")
            else:
                st.success("Conferência gravada.")
                st.rerun()

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
        ["Premiação M1 (R$)", "Premiação recorrente (R$)"]
    ].sum()
    if not visible_clients.empty:
        visible_clients = visible_clients.drop(columns=["Premiação M1 (R$)", "Premiação recorrente (R$)", "Total apurado (R$)"])
        visible_clients = visible_clients.merge(results, on=["Vendedor", "Cliente"], how="left")
        visible_clients["Total apurado (R$)"] = visible_clients["Premiação M1 (R$)"] + visible_clients["Premiação recorrente (R$)"]

total_first = money(view["Premiação M1 (R$)"].sum())
total_recurring = money(view["Premiação recorrente (R$)"].sum())
total_billed = money(view["Valor faturado (R$)"].sum())
pending = int(view["Status"].eq("PENDENTE COMPROVAÇÃO").sum())
render_kpis([
    {"label": "Total elegível apurado", "value": _brl(total_first+total_recurring), "detail": "M1 + bônus recebido M1–M3", "accent": "#2563eb"},
    {"label": "Premiação não recorrente", "value": _brl(total_first), "detail": "10%, 15% ou 20% de M1", "accent": "#0f766e"},
    {"label": "Bônus recorrente", "value": _brl(total_recurring), "detail": "Faixa 0% / 2% / 3% / 4%", "accent": "#7c3aed"},
    {"label": "Faturamento exibido", "value": _brl(total_billed), "detail": "Inclui pendências", "accent": "#475569"},
    {"label": "Pendências de comprovação", "value": str(pending), "detail": "Sem liberação para pagar", "accent": "#dc2626"},
])

st.markdown("### Consolidado por vendedor")
if view.empty:
    grouped = pd.DataFrame(columns=["Vendedor", "Faturamento (R$)", "Premiação M1 (R$)", "Premiação recorrente (R$)", "Total apurado (R$)"])
else:
    grouped = view.groupby("Vendedor", as_index=False).agg({
        "Valor faturado (R$)": "sum", "Premiação M1 (R$)": "sum", "Premiação recorrente (R$)": "sum",
    }).rename(columns={"Valor faturado (R$)": "Faturamento (R$)"})
    grouped["Total apurado (R$)"] = grouped["Premiação M1 (R$)"] + grouped["Premiação recorrente (R$)"]
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
    st.dataframe(view[view["Fatura"] == "M1"].drop(columns=["ID", "Contrato"], errors="ignore"), hide_index=True, use_container_width=True)
with client_tab:
    st.dataframe(visible_clients, hide_index=True, use_container_width=True)
with recurring_tab:
    st.dataframe(view.drop(columns=["ID", "Contrato"], errors="ignore"), hide_index=True, use_container_width=True)
with checks_tab:
    problem = view[view["Status"] != "APURADA"]
    st.dataframe(problem.drop(columns=["ID", "Contrato"], errors="ignore"), hide_index=True, use_container_width=True)
    st.warning("O sistema não faz liquidação ou pagamento automático de comissão. Os valores são apurações, não comprovantes de repasse.")

output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    grouped.to_excel(writer, index=False, sheet_name="Por Vendedor")
    visible_clients.to_excel(writer, index=False, sheet_name="Por Cliente")
    view.drop(columns=["ID", "Contrato"], errors="ignore").to_excel(writer, index=False, sheet_name="Faturas M1-M3")
st.download_button(
    "Baixar apuração em Excel", data=output.getvalue(),
    file_name="comissoes_meta5_verdio.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
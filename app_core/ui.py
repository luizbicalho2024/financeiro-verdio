from __future__ import annotations

import base64
import html
import logging
from pathlib import Path
from typing import Any

import streamlit as st

from app_core.auth import is_admin, is_authenticated, logout, role_label, user_name
from app_core.branding import normalize_branding, readable_text_color
from app_core.settings import decode_logo, get_branding

log = logging.getLogger("financeiro_verdio.ui")
ROOT = Path(__file__).resolve().parents[1]
FALLBACK_LOGO = ROOT / "imgs" / "v-c.png"


def configure_page(title: str, *, layout: str = "wide", icon: str = "💳") -> None:
    st.set_page_config(
        page_title=title,
        page_icon=icon,
        layout=layout,
        initial_sidebar_state="expanded",
    )


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = str(hex_color).lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _rgba(hex_color: str, alpha: float) -> str:
    red, green, blue = _hex_to_rgb(hex_color)
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _apply_plotly_theme(branding: dict[str, Any]) -> None:
    try:
        import plotly.graph_objects as go
        import plotly.io as pio

        pio.templates["financeiro_verdio"] = go.layout.Template(
            layout={
                "paper_bgcolor": branding["surface_color"],
                "plot_bgcolor": branding["surface_color"],
                "font": {"color": branding["text_color"]},
                "title": {"font": {"color": branding["text_color"]}},
                "legend": {"font": {"color": branding["text_color"]}},
                "colorway": [
                    branding["primary_color"],
                    branding["secondary_color"],
                    branding["accent_color"],
                    "#64748B",
                    "#0F766E",
                    "#7C3AED",
                ],
                "xaxis": {
                    "gridcolor": branding["border_color"],
                    "zerolinecolor": branding["border_color"],
                },
                "yaxis": {
                    "gridcolor": branding["border_color"],
                    "zerolinecolor": branding["border_color"],
                },
            }
        )
        pio.templates.default = "financeiro_verdio"
    except Exception:
        log.debug("Não foi possível aplicar o template do Plotly.", exc_info=True)


def apply_branding() -> dict[str, Any]:
    branding = normalize_branding(get_branding())
    primary_text = readable_text_color(branding["primary_color"])
    secondary_text = readable_text_color(branding["secondary_color"])
    input_focus = _rgba(branding["primary_color"], 0.22)
    hover_surface = _rgba(branding["primary_color"], 0.08)
    subtle_primary = _rgba(branding["primary_color"], 0.12)
    border_strong = _rgba(branding["text_color"], 0.30)

    css = f"""
    <style>
      :root {{
        --fv-primary: {branding['primary_color']};
        --fv-secondary: {branding['secondary_color']};
        --fv-accent: {branding['accent_color']};
        --fv-bg: {branding['background_color']};
        --fv-surface: {branding['surface_color']};
        --fv-text: {branding['text_color']};
        --fv-muted: {branding['muted_text_color']};
        --fv-border: {branding['border_color']};
        --fv-input-bg: {branding['input_background_color']};
        --fv-sidebar-bg: {branding['sidebar_background_color']};
        --fv-sidebar-text: {branding['sidebar_text_color']};
        --fv-sidebar-muted: {branding['sidebar_muted_color']};
        --fv-on-primary: {primary_text};
        --fv-on-secondary: {secondary_text};
      }}

      html, body, [data-testid="stAppViewContainer"], .stApp {{
        background: var(--fv-bg) !important;
        color: var(--fv-text) !important;
      }}

      [data-testid="stAppViewBlockContainer"] {{
        max-width: 1500px;
        padding-top: 1.8rem;
        padding-bottom: 3rem;
      }}

      [data-testid="stHeader"] {{
        background: transparent !important;
      }}

      [data-testid="stSidebar"] > div:first-child {{
        background: var(--fv-sidebar-bg) !important;
        border-right: 1px solid rgba(255,255,255,.08);
      }}

      [data-testid="stSidebar"] * {{
        scrollbar-color: rgba(255,255,255,.25) transparent;
      }}

      [data-testid="stSidebarNav"] {{ display: none !important; }}

      [data-testid="stSidebar"] h1,
      [data-testid="stSidebar"] h2,
      [data-testid="stSidebar"] h3,
      [data-testid="stSidebar"] p,
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] span {{
        color: var(--fv-sidebar-text);
      }}

      [data-testid="stSidebar"] small,
      [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
        color: var(--fv-sidebar-muted) !important;
      }}

      [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{
        border-radius: 10px;
        padding: .48rem .62rem;
        margin: .08rem 0;
        transition: background-color .16s ease, transform .16s ease;
      }}

      [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{
        background: rgba(255,255,255,.08) !important;
        transform: translateX(2px);
      }}

      h1, h2, h3, h4, h5, h6 {{
        color: var(--fv-text) !important;
        letter-spacing: -0.02em;
      }}

      p, li, label, [data-testid="stMarkdownContainer"] {{
        color: var(--fv-text);
      }}

      [data-testid="stCaptionContainer"] p,
      .fv-muted {{
        color: var(--fv-muted) !important;
      }}

      hr {{
        border-color: var(--fv-border) !important;
        opacity: .85;
      }}

      /* Campos: borda visível em todos os estados. */
      [data-baseweb="input"] > div,
      [data-baseweb="base-input"],
      [data-baseweb="select"] > div,
      [data-baseweb="textarea"] > div,
      [data-baseweb="datepicker"] > div,
      [data-testid="stNumberInput"] [data-baseweb="input"] > div,
      [data-testid="stFileUploaderDropzone"],
      [data-testid="stDataEditor"] {{
        background: var(--fv-input-bg) !important;
        border: 1px solid {border_strong} !important;
        border-radius: 10px !important;
        box-shadow: none !important;
      }}

      [data-baseweb="input"] > div:hover,
      [data-baseweb="select"] > div:hover,
      [data-baseweb="textarea"] > div:hover,
      [data-baseweb="datepicker"] > div:hover,
      [data-testid="stFileUploaderDropzone"]:hover {{
        border-color: var(--fv-primary) !important;
      }}

      [data-baseweb="input"] > div:focus-within,
      [data-baseweb="select"] > div:focus-within,
      [data-baseweb="textarea"] > div:focus-within,
      [data-baseweb="datepicker"] > div:focus-within {{
        border-color: var(--fv-primary) !important;
        box-shadow: 0 0 0 3px {input_focus} !important;
      }}

      input, textarea,
      [data-baseweb="select"] input,
      [data-baseweb="select"] span {{
        color: var(--fv-text) !important;
        caret-color: var(--fv-primary) !important;
      }}

      input::placeholder, textarea::placeholder {{
        color: var(--fv-muted) !important;
        opacity: .78;
      }}

      [data-baseweb="popover"],
      [data-baseweb="menu"],
      [role="listbox"] {{
        background: var(--fv-surface) !important;
        border-color: var(--fv-border) !important;
      }}

      [role="option"] {{ color: var(--fv-text) !important; }}
      [role="option"]:hover,
      [role="option"][aria-selected="true"] {{
        background: {hover_surface} !important;
      }}

      /* Botões */
      .stButton > button[kind="primary"],
      .stFormSubmitButton > button[kind="primary"],
      [data-testid="stDownloadButton"] > button[kind="primary"],
      button[data-testid="stBaseButton-primary"] {{
        background: var(--fv-primary) !important;
        color: var(--fv-on-primary) !important;
        border-color: var(--fv-primary) !important;
      }}

      .stButton > button,
      .stFormSubmitButton > button,
      [data-testid="stDownloadButton"] > button {{
        min-height: 2.55rem;
        border-radius: 10px !important;
        font-weight: 650 !important;
        border: 1px solid var(--fv-border) !important;
        transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
      }}

      .stButton > button:hover,
      .stFormSubmitButton > button:hover,
      [data-testid="stDownloadButton"] > button:hover {{
        transform: translateY(-1px);
        border-color: var(--fv-primary) !important;
        box-shadow: 0 8px 20px {subtle_primary};
      }}

      /* Tabs, toggles e seleção */
      div[data-baseweb="tab-highlight"] {{ background-color: var(--fv-primary) !important; }}
      button[data-baseweb="tab"][aria-selected="true"] {{ color: var(--fv-primary) !important; }}
      [data-testid="stCheckbox"] input:checked + div,
      [data-testid="stToggle"] input:checked + div,
      [data-testid="stRadio"] input:checked + div {{
        background-color: var(--fv-primary) !important;
        border-color: var(--fv-primary) !important;
      }}
      [data-testid="stProgress"] > div > div > div,
      [data-testid="stSlider"] [role="slider"] {{
        background-color: var(--fv-primary) !important;
      }}

      /* Cartões, métricas, formulários e expanders */
      [data-testid="stMetric"],
      [data-testid="stForm"],
      [data-testid="stExpander"],
      .fv-card {{
        background: var(--fv-surface) !important;
        border: 1px solid var(--fv-border) !important;
        border-radius: 14px !important;
        box-shadow: 0 8px 28px rgba(15,23,42,.045);
      }}

      [data-testid="stMetric"] {{
        padding: 1rem 1.05rem;
        min-height: 108px;
      }}
      [data-testid="stMetricLabel"] p {{ color: var(--fv-muted) !important; }}
      [data-testid="stMetricValue"] {{ color: var(--fv-text) !important; }}

      [data-testid="stForm"] {{ padding: 1rem 1.1rem; }}
      [data-testid="stExpander"] details {{ border-radius: 14px; }}

      [data-testid="stDataFrame"],
      [data-testid="stTable"] {{
        border: 1px solid var(--fv-border);
        border-radius: 12px;
        overflow: hidden;
        background: var(--fv-surface);
      }}

      /* Alertas */
      [data-testid="stAlert"] {{
        border-radius: 12px !important;
        border-width: 1px !important;
      }}

      /* Header corporativo reutilizável */
      .fv-hero {{
        background: linear-gradient(135deg, var(--fv-secondary), var(--fv-primary));
        border-radius: 18px;
        padding: 1.45rem 1.65rem;
        margin: .15rem 0 1.35rem;
        box-shadow: 0 14px 38px rgba(15,23,42,.13);
      }}
      .fv-hero h1 {{ color: var(--fv-on-secondary) !important; margin: 0; font-size: 2rem; }}
      .fv-hero p {{ color: var(--fv-on-secondary) !important; opacity: .86; margin: .45rem 0 0; }}

      .fv-card {{ padding: 1.05rem 1.15rem; height: 100%; }}
      .fv-card-title {{ color: var(--fv-muted); font-size: .78rem; font-weight: 750; text-transform: uppercase; letter-spacing: .06em; }}
      .fv-card-value {{ color: var(--fv-text); font-size: 1.28rem; font-weight: 760; margin-top: .28rem; }}
      .fv-card-copy {{ color: var(--fv-muted); font-size: .92rem; line-height: 1.45; margin-top: .4rem; }}

      .fv-session {{
        background: rgba(255,255,255,.07);
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 12px;
        padding: .75rem .8rem;
        margin: .55rem 0 .65rem;
      }}
      .fv-session-name {{ color: var(--fv-sidebar-text); font-weight: 750; }}
      .fv-session-role {{ color: var(--fv-sidebar-muted); font-size: .82rem; margin-top: .18rem; }}

      .fv-logo {{ display:flex; align-items:center; width:fit-content; max-width:100%; margin:.15rem 0 .85rem; }}
      .fv-logo img {{ display:block; width:auto; height:auto; max-width:100%; max-height:145px; object-fit:contain; }}
      .fv-logo-sidebar img {{ max-height:100px; }}

      #MainMenu {{ visibility: hidden; }}
      footer {{ visibility: hidden; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    _apply_plotly_theme(branding)
    return branding


def _logo_data_uri(*, sidebar: bool, branding: dict[str, Any]) -> str | None:
    raw, mime = decode_logo(branding, sidebar=sidebar)
    if raw:
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:{mime or 'image/png'};base64,{encoded}"

    if FALLBACK_LOGO.exists():
        encoded = base64.b64encode(FALLBACK_LOGO.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    return None


def render_logo(*, sidebar: bool = False, max_width: int = 260, branding: dict[str, Any] | None = None) -> None:
    branding = normalize_branding(branding or get_branding())
    data_uri = _logo_data_uri(sidebar=sidebar, branding=branding)
    if not data_uri:
        return

    safe_width = max(90, min(int(max_width), 720))
    class_name = "fv-logo fv-logo-sidebar" if sidebar else "fv-logo"
    markup = (
        f'<div class="{class_name}" style="width:min(100%, {safe_width}px)">'
        f'<img src="{data_uri}" alt="Logomarca do sistema" style="max-width:{safe_width}px" />'
        "</div>"
    )
    target = st.sidebar if sidebar else st
    target.markdown(markup, unsafe_allow_html=True)


def render_hero(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <section class="fv-hero">
          <h1>{html.escape(str(title))}</h1>
          <p>{html.escape(str(subtitle))}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_card(title: str, value: str, copy: str = "") -> None:
    st.markdown(
        f"""
        <div class="fv-card">
          <div class="fv-card-title">{html.escape(str(title))}</div>
          <div class="fv-card-value">{html.escape(str(value))}</div>
          <div class="fv-card-copy">{html.escape(str(copy))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    branding = normalize_branding(get_branding())
    render_logo(sidebar=True, max_width=200, branding=branding)
    st.sidebar.markdown(f"### {html.escape(branding['system_name'])}")
    st.sidebar.caption(branding["system_subtitle"])

    if is_authenticated():
        st.sidebar.markdown(
            f"""
            <div class="fv-session">
              <div class="fv-session-name">{html.escape(user_name())}</div>
              <div class="fv-session-role">{html.escape(role_label())}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.sidebar.button("Sair da plataforma", key="fv_global_logout", use_container_width=True):
            logout()

        st.sidebar.markdown("---")
        st.sidebar.caption("Financeiro")
        st.sidebar.page_link("1_Home.py", label="Visão geral")
        st.sidebar.page_link("pages/5_Faturamento_Verdio_Completo.py", label="Faturamento Verdio — completo")
        st.sidebar.page_link("pages/6_Faturamento_Parceiros.py", label="Faturamento parceiros")
        st.sidebar.page_link("pages/6_Resumo_Faturamento_Mensal.py", label="Resumo mensal")
        st.sidebar.page_link("pages/7_Historico_Faturamento.py", label="Histórico de faturamento")
        st.sidebar.page_link("pages/4_Relatorio_SUGESP_Detalhado.py", label="Relatório SUGESP")

        if is_admin():
            st.sidebar.markdown("---")
            st.sidebar.caption("Gestão")
            st.sidebar.page_link("pages/7_Contratos_Clientes.py", label="Contratos e preços")
            st.sidebar.page_link("pages/8_Comissao_Vendedores.py", label="Comissões")
            st.sidebar.page_link("pages/94_Gestao_Estoque.py", label="Estoque e tabelas")
            st.sidebar.page_link("pages/2_Gerenciar_Usuarios.py", label="Usuários")
            st.sidebar.page_link("pages/90_Identidade_Visual.py", label="Identidade visual")
            st.sidebar.page_link("pages/99_Logs_do_Sistema.py", label="Auditoria e logs")

            with st.sidebar.expander("Compatibilidade", expanded=False):
                st.page_link("pages/6_Faturamento_Verdio.py", label="Faturamento Verdio — legado")

    footer = str(branding.get("footer_text") or "").strip()
    if footer:
        st.sidebar.markdown("---")
        st.sidebar.caption(footer)

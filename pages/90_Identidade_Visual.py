from __future__ import annotations

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st

from app_core.auth import require_auth, user_email
from app_core.branding import branding_contrast_warnings, normalize_branding
from app_core.settings import (
    get_branding,
    reset_branding_colors,
    reset_logo,
    save_branding,
    update_logo,
)
from app_core.ui import apply_branding, render_card, render_hero, render_logo, render_sidebar
import user_management_db as umdb

st.set_page_config(page_title="Identidade visual", page_icon="🎨", layout="wide")
apply_branding()
require_auth(admin=True)
render_sidebar()
render_hero(
    "Identidade visual",
    "Personalize a marca do sistema sem alterar código: logos, cores, títulos e apresentação da interface.",
)

branding = normalize_branding(get_branding())

tab_brand, tab_logos, tab_preview = st.tabs(["Marca e cores", "Logomarcas", "Pré-visualização"])

with tab_brand:
    st.caption("As configurações ficam armazenadas no MongoDB e são aplicadas em todas as páginas após o salvamento.")

    with st.form("branding_form"):
        st.markdown("#### Identificação")
        name_col, subtitle_col = st.columns([1, 2])
        system_name = name_col.text_input("Nome do sistema", value=branding["system_name"])
        system_subtitle = subtitle_col.text_input("Subtítulo", value=branding["system_subtitle"])
        footer_text = st.text_input("Texto do rodapé da sidebar", value=branding["footer_text"])

        st.markdown("#### Cores principais")
        c1, c2, c3 = st.columns(3)
        primary = c1.color_picker("Cor primária", value=branding["primary_color"])
        secondary = c2.color_picker("Cor secundária", value=branding["secondary_color"])
        accent = c3.color_picker("Cor de destaque", value=branding["accent_color"])

        st.markdown("#### Conteúdo")
        c1, c2, c3 = st.columns(3)
        background = c1.color_picker("Fundo do sistema", value=branding["background_color"])
        surface = c2.color_picker("Cartões e superfícies", value=branding["surface_color"])
        text = c3.color_picker("Texto principal", value=branding["text_color"])

        c1, c2, c3 = st.columns(3)
        muted = c1.color_picker("Texto secundário", value=branding["muted_text_color"])
        border = c2.color_picker("Bordas", value=branding["border_color"])
        input_background = c3.color_picker("Fundo dos campos", value=branding["input_background_color"])

        st.markdown("#### Barra lateral")
        c1, c2, c3 = st.columns(3)
        sidebar_background = c1.color_picker("Fundo da sidebar", value=branding["sidebar_background_color"])
        sidebar_text = c2.color_picker("Texto da sidebar", value=branding["sidebar_text_color"])
        sidebar_muted = c3.color_picker("Texto secundário da sidebar", value=branding["sidebar_muted_color"])

        save = st.form_submit_button("Salvar identidade visual", type="primary", use_container_width=True)

    candidate = dict(branding)
    candidate.update(
        {
            "system_name": system_name,
            "system_subtitle": system_subtitle,
            "footer_text": footer_text,
            "primary_color": primary,
            "secondary_color": secondary,
            "accent_color": accent,
            "background_color": background,
            "surface_color": surface,
            "text_color": text,
            "muted_text_color": muted,
            "border_color": border,
            "input_background_color": input_background,
            "sidebar_background_color": sidebar_background,
            "sidebar_text_color": sidebar_text,
            "sidebar_muted_color": sidebar_muted,
        }
    )

    warnings = branding_contrast_warnings(candidate)
    if warnings:
        st.warning("A combinação pode dificultar a leitura: " + " ".join(warnings))

    if save:
        if not system_name.strip():
            st.error("O nome do sistema é obrigatório.")
        elif save_branding(candidate):
            umdb.log_action("INFO", user_email(), "Identidade visual atualizada.")
            st.success("Identidade visual salva.")
            st.rerun()
        else:
            st.error("Não foi possível salvar a identidade visual.")

    if st.button("Restaurar textos e cores padrão", use_container_width=False):
        if reset_branding_colors():
            umdb.log_action("WARNING", user_email(), "Textos e cores da identidade visual restaurados.")
            st.rerun()

with tab_logos:
    st.caption(
        "São duas imagens independentes. A principal aparece no login e em conteúdos institucionais; "
        "a segunda é exclusiva da barra lateral. O sistema otimiza automaticamente as imagens antes de salvar."
    )

    main_col, sidebar_col = st.columns(2)
    with main_col:
        st.markdown("#### Logo principal e login")
        render_logo(max_width=300, branding=branding)
        main_upload = st.file_uploader(
            "Nova logo principal",
            type=["png", "jpg", "jpeg", "webp"],
            key="branding_main_logo",
        )
        if main_upload is not None:
            st.image(main_upload, width=260)
            if st.button("Aplicar logo principal", type="primary", key="apply_main_logo"):
                ok, error = update_logo(main_upload.getvalue(), main_upload.name, sidebar=False)
                if ok:
                    umdb.log_action("INFO", user_email(), "Logo principal atualizada.")
                    st.rerun()
                st.error(error or "Não foi possível atualizar a logo principal.")

        if st.button("Usar logo padrão do projeto", key="reset_main_logo"):
            if reset_logo(sidebar=False):
                umdb.log_action("WARNING", user_email(), "Logo principal restaurada para o padrão.")
                st.rerun()

    with sidebar_col:
        st.markdown("#### Logo da sidebar")
        st.info("A prévia real fica na barra lateral à esquerda.")
        sidebar_upload = st.file_uploader(
            "Nova logo da sidebar",
            type=["png", "jpg", "jpeg", "webp"],
            key="branding_sidebar_logo",
        )
        if sidebar_upload is not None:
            st.image(sidebar_upload, width=240)
            if st.button("Aplicar logo da sidebar", type="primary", key="apply_sidebar_logo"):
                ok, error = update_logo(sidebar_upload.getvalue(), sidebar_upload.name, sidebar=True)
                if ok:
                    umdb.log_action("INFO", user_email(), "Logo da sidebar atualizada.")
                    st.rerun()
                st.error(error or "Não foi possível atualizar a logo da sidebar.")

        if st.button("Usar logo principal também na sidebar", key="reset_sidebar_logo"):
            if reset_logo(sidebar=True):
                umdb.log_action("WARNING", user_email(), "Logo exclusiva da sidebar removida.")
                st.rerun()

with tab_preview:
    st.markdown("#### Componentes")
    preview_cols = st.columns(3)
    with preview_cols[0]:
        render_card("Receita", "R$ 128.450,00", "Exemplo de cartão financeiro")
    with preview_cols[1]:
        render_card("Clientes", "42", "Exemplo de indicador operacional")
    with preview_cols[2]:
        render_card("Status", "Em dia", "Exemplo de situação consolidada")

    st.markdown("#### Campos e ações")
    c1, c2 = st.columns(2)
    c1.text_input("Campo de texto", placeholder="A borda deve permanecer visível")
    c2.number_input("Campo numérico", value=1250.00, format="%.2f")
    c1.selectbox("Seleção", ["Opção A", "Opção B", "Opção C"])
    c2.date_input("Data")
    st.button("Ação secundária")
    st.button("Ação principal", type="primary")

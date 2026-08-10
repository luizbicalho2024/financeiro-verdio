from app_core.branding import contrast_ratio, normalize_branding, readable_text_color


def test_normalize_branding_migrates_partial_document():
    branding = normalize_branding({"system_name": "Teste", "primary_color": "#123456"})
    assert branding["system_name"] == "Teste"
    assert branding["primary_color"] == "#123456"
    assert branding["sidebar_background_color"].startswith("#")


def test_invalid_color_falls_back():
    branding = normalize_branding({"primary_color": "azul"})
    assert branding["primary_color"] == "#006494"


def test_contrast_ratio_black_white():
    assert contrast_ratio("#000000", "#FFFFFF") > 20


def test_readable_text_color_returns_supported_color():
    assert readable_text_color("#000000") == "#FFFFFF"
    assert readable_text_color("#FFFFFF") == "#111827"

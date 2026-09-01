from pathlib import Path


def test_bulk_history_is_resumable_one_period_per_rerun() -> None:
    source = Path("pages/5_Faturamento_Verdio_Completo.py").read_text(
        encoding="utf-8"
    )
    assert 'BULK_JOB_KEY = "billing_bulk_history_job"' in source
    assert '"next_index": 0' in source
    assert '"running": True' in source
    assert "bulk_mode=True" in source
    assert "st.rerun()" in source
    assert "Ao concluir este mês, a página continuará automaticamente" in source
    assert "Progresso da carga histórica" in source


def test_bulk_history_no_long_monolithic_period_loop() -> None:
    source = Path("pages/5_Faturamento_Verdio_Completo.py").read_text(
        encoding="utf-8"
    )
    assert "for index, periodo in enumerate(ordered_periods, start=1):" not in source


def test_bulk_mode_suppresses_per_client_database_audit() -> None:
    page = Path("pages/5_Faturamento_Verdio_Completo.py").read_text(
        encoding="utf-8"
    )
    userdb = Path("user_management_db.py").read_text(encoding="utf-8")
    assert "bulk_mode: bool = False" in page
    assert "audit=not bulk_mode" in page
    assert "audit: bool = True" in userdb
    assert "if audit:" in userdb

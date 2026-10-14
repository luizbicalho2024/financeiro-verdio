"""Politica Meta 5 Verdio (Bionio Frotas) - funcoes puras e testaveis.

A meta de instalacoes usa 25 / vendedores atuantes. O desconto compara a
receita negociada ponderada com o valor de tabela na data do contrato.
A verificacao de recebimento/atividade pertence a camada de apuracao.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

BASE_TARGET = Decimal("25")
MAX_DISCOUNT = Decimal("15")


def _d(value: object) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("Valor numerico ausente ou invalido")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Valor numerico nao finito")
    return number


def money(value: object) -> float:
    return float(_d(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def target_for_seller(active_sellers: int) -> Decimal:
    if not isinstance(active_sellers, int) or isinstance(active_sellers, bool) or active_sellers <= 0:
        raise ValueError("Informe o numero positivo de vendedores atuantes")
    return BASE_TARGET / Decimal(active_sellers)


def installation_attainment(installed: int, active_sellers: int) -> Decimal:
    if not isinstance(installed, int) or isinstance(installed, bool) or installed < 0:
        raise ValueError("Quantidade instalada invalida")
    return Decimal(installed) * Decimal(active_sellers) / BASE_TARGET * Decimal(100)


def first_month_percent(attainment_percent: object) -> Decimal:
    pct = _d(attainment_percent)
    if pct < Decimal("80"):
        return Decimal("0")
    if pct < Decimal("100"):
        return Decimal("10")
    if pct < Decimal("110"):
        return Decimal("15")
    return Decimal("20")


def recurring_percent(seller_month_revenue: object) -> Decimal:
    value = _d(seller_month_revenue)
    if value <= Decimal("2000"):
        return Decimal("0")
    if value <= Decimal("5000"):
        return Decimal("2")
    if value <= Decimal("12000"):
        return Decimal("3")
    return Decimal("4")


def percent_reward(amount: object, rate: object) -> float:
    return money(_d(amount) * _d(rate) / Decimal(100))


def contract_discount(
    negotiated: Mapping[str, object],
    quantities: Mapping[str, object],
    table_prices: Mapping[str, object],
) -> tuple[float | None, str]:
    """Calcula desconto do contrato ponderado por quantidade.

    Bloqueia a apuracao se faltarem precos de tabela ou dados negociados de
    qualquer produto com quantidade positiva. Nao confunde desconto e margem.
    """
    total_table = Decimal(0)
    total_sold = Decimal(0)
    considered = 0
    try:
        for product, raw_qty in quantities.items():
            qty = _d(raw_qty)
            if qty < 0 or qty != qty.to_integral_value():
                return None, "Quantidade contratada invalida"
            if qty == 0:
                continue
            considered += 1
            if product not in negotiated or product not in table_prices:
                return None, f"Preco sem referencia oficial: {product}"
            base = _d(table_prices[product])
            sold = _d(negotiated[product])
            if base <= 0 or sold <= 0:
                return None, f"Preco sem referencia oficial: {product}"
            total_table += base * qty
            total_sold += sold * qty
    except (ValueError, ArithmeticError, TypeError) as exc:
        return None, f"Dados economicos invalidos: {exc}"
    if not considered or total_table <= 0:
        return None, "Contrato sem equipamentos/precos completos"
    discount = max(Decimal(0), (total_table - total_sold) / total_table * Decimal(100))
    return float(discount), "Referencia contratual validada"


def discount_is_eligible(discount: float | None) -> bool:
    return discount is not None and _d(discount) <= MAX_DISCOUNT


def shift_month(period: str, offset: int) -> str:
    parts = period.split("-")
    if len(parts) != 2:
        raise ValueError("Competencia deve estar no formato AAAA-MM")
    year, month = int(parts[0]), int(parts[1])
    if len(parts[0]) != 4 or len(parts[1]) != 2 or not (1 <= month <= 12):
        raise ValueError("Competencia deve estar no formato AAAA-MM")
    number = year * 12 + (month - 1) + offset
    y, m = divmod(number, 12)
    return f"{y:04d}-{m+1:02d}"
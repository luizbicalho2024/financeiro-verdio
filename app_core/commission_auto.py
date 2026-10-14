"""Funcoes puras para apuracao automatica da Meta 5.

Vendas faturadas do cadastro de contratos nao comprovam instalacao.
Receita faturada nao significa recebimento; retorno None indica dado ausente.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
import unicodedata


def norm(value: object) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).casefold().split())


def month_key(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m')
    text = str(value or '').strip()
    if len(text) >= 7 and text[4] == '-' and text[5:7].isdigit() and text[:4].isdigit():
        return text[:7] if 1 <= int(text[5:7]) <= 12 else ''
    if len(text) >= 10 and text[2] == '/' and text[5] == '/':
        try:
            return datetime.strptime(text[:10], '%d/%m/%Y').strftime('%Y-%m')
        except ValueError:
            pass
    return ''


def sold_units_by_seller(
    contracts: Mapping[str, Mapping[str, Any]],
    billed_months_by_client: Mapping[str, set[str]],
) -> dict[str, dict[str, int]]:
    """Conta unidades de contratos com venda atribuida e faturamento positivo.

    O mes da venda e o mes de assinatura do contrato. Cada documento de
    contrato e contado uma vez. Não se infere instalacao do estoque.
    """
    result: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for doc_id, contract in contracts.items():
        seller = str(contract.get('vendedor') or '').strip()
        client = str(contract.get('cliente') or doc_id).strip()
        period = month_key(contract.get('ultima_atualizacao_termo'))
        if not seller or not period:
            continue
        if not any(m >= period for m in billed_months_by_client.get(norm(client), set())):
            continue
        if contract.get('ativo') is False or contract.get('cancelado') is True:
            continue
        status = norm(contract.get('status_contrato') or '')
        if status in {'cancelado', 'cancelada', 'rascunho', 'excluido', 'inativo'}:
            continue
        quantities = contract.get('quantidades_produtos') or {}
        if not isinstance(quantities, dict):
            continue
        qty = 0
        invalid = False
        for value in quantities.values():
            try:
                amount = Decimal(str(value))
                if not amount.is_finite() or amount < 0 or amount != int(amount):
                    invalid = True
                    break
                qty += int(amount)
            except (InvalidOperation, ValueError, TypeError, OverflowError):
                invalid = True
                break
        if invalid or qty <= 0:
            continue
        result[period][seller] += qty
    return {m: dict(sellers) for m, sellers in result.items()}


def payment_confirmed(record: Mapping[str, Any] | None, billed: float) -> bool | None:
    """True/False se há campo financeiro EXPLICITO; None sem informacao.

    Ignora 'status' genérico e billing_history.status='closed': fechamento
    do relatorio nao equivale a fatura liquidada.
    """
    if not record or billed <= 0:
        return None
    for field in ('pagamento_confirmado', 'fatura_paga', 'recebimento_confirmado'):
        if isinstance(record.get(field), bool):
            return bool(record[field])
    for field in ('status_pagamento', 'situacao_pagamento'):
        value = norm(record.get(field))
        if value in {'pago', 'paga', 'liquidado', 'liquidada', 'recebido', 'recebida', 'quitado', 'quitada'}:
            return True
        if value in {'pendente', 'em aberto', 'vencido', 'vencida', 'nao pago', 'nao paga', 'cancelado', 'cancelada'}:
            return False
    for field in ('valor_recebido', 'valor_pago'):
        if record.get(field) not in (None, ''):
            try:
                amount = Decimal(str(record[field]))
                if amount.is_finite():
                    return amount >= Decimal(str(billed)) - Decimal('0.01')
            except (InvalidOperation, ValueError, TypeError):
                pass
    return None


def activity_confirmed(record: Mapping[str, Any] | None) -> bool | None:
    """Somente declara confirmacao com um campo de atividade explicito."""
    if not record:
        return None
    for field in ('dispositivos_ativos_confirmados', 'atividade_confirmada'):
        if isinstance(record.get(field), bool):
            return bool(record[field])
    return None
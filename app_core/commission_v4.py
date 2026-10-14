"""Apuração compartilhada Meta 5: somente a janela M1-M3.

Não confunde vendas com instalações nem emissão de faturas com liquidação.
Sem integração de pagamento, apresenta previsão sem afirmar que é liberável.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Callable, Mapping

from app_core.commission_auto import (
    activity_confirmed, month_key, norm, payment_confirmed, sold_units_by_seller,
)
from app_core.commission_policy import (
    contract_discount, discount_is_eligible, first_month_percent,
    installation_attainment, money, percent_reward, recurring_percent,
    shift_month, target_for_seller,
)

MONTHS_ABBR = ('jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez')


def period_label(period: str) -> str:
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', str(period or '')):
        return str(period or '')
    return f'{MONTHS_ABBR[int(period[5:7])-1]}/{period[:4]}'


def band(revenue: object) -> str:
    amount = float(revenue or 0)
    if amount <= 2000:
        return 'Sem bônus'
    if amount <= 5000:
        return 'Prata'
    if amount <= 12000:
        return 'Ouro'
    return 'Diamante'


def unit_target(active_sellers: int) -> float:
    return float(target_for_seller(active_sellers)) if active_sellers else 0.0


def eligible_roster(contracts: Mapping[str, Mapping[str, Any]], period: str) -> list[str]:
    """Vendedores com carteira contratual ativa no mês, mesmo que sem vendas."""
    people: dict[str,str] = {}
    for doc_id, c in contracts.items():
        seller = str(c.get('vendedor') or '').strip()
        signed = month_key(c.get('ultima_atualizacao_termo'))
        expiry = month_key(c.get('vencimento_contrato'))
        if not seller or not signed or signed > period or (expiry and expiry < period):
            continue
        if c.get('ativo') is False or c.get('cancelado') is True:
            continue
        if norm(c.get('status_contrato')) in {'cancelado','cancelada','rascunho','excluido','inativo'}:
            continue
        people.setdefault(norm(seller),seller)
    return sorted(people.values(),key=str.casefold)


def contract_monthly_value(contract: Mapping[str,Any]) -> float:
    prices = contract.get('precos_produtos') or {}
    quantities = contract.get('quantidades_produtos') or {}
    if not isinstance(prices,dict) or not isinstance(quantities,dict):
        return 0.0
    amount = 0.0
    for product, count in quantities.items():
        try:
            qty = float(count)
            price = float(prices.get(product) or 0)
            if qty < 0 or price < 0 or not qty.is_integer():
                return 0.0
            amount += qty * price
        except (ValueError,TypeError,OverflowError):
            return 0.0
    return money(amount)


def commercial_totals(contracts: Mapping[str,Mapping[str,Any]], period: str) -> dict[str,float]:
    totals: dict[str,float] = defaultdict(float)
    for doc_id,c in contracts.items():
        seller = str(c.get('vendedor') or '').strip()
        if seller and month_key(c.get('ultima_atualizacao_termo')) == period:
            discount, _ = contract_discount(c.get('precos_produtos') or {}, c.get('quantidades_produtos') or {}, c.get('precos_tabela_produtos') or {})
            if not discount_is_eligible(discount):
                continue
            if c.get('ativo') is False or c.get('cancelado') is True or norm(c.get('status_contrato')) in {'cancelado','cancelada','rascunho','excluido','inativo'}:
                continue
            totals[seller] += contract_monthly_value(c)
    return {k:money(v) for k,v in totals.items()}


def commission_id(contract_id: str, client: str, period: str, component: str) -> str:
    if component not in {'M1','RECORRENTE'}:
        raise ValueError('Componente não suportado')
    raw = f'meta5-v4|{contract_id}|{norm(client)}|{period}|{component}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _float(raw: object) -> float:
    try:
        if isinstance(raw,str):
            raw = raw.replace('R$','').replace(' ','')
            if ',' in raw and '.' in raw:
                raw=raw.replace('.','').replace(',','.')
            elif ',' in raw:
                raw=raw.replace(',','.')
        return float(raw or 0)
    except (ValueError,TypeError):
        return 0.0


def billed_total(record: dict | None, item_reader: Callable[[dict],list[dict]]) -> float:
    if not record:
        return 0.0
    if record.get('valor_total') not in ('',None):
        return money(max(0,_float(record['valor_total'])))
    value = 0.0
    for item in item_reader(record):
        if norm(item.get('Categoria') or item.get('categoria')) == 'suspenso':
            continue
        for key in ('Valor a Faturar','valor_faturado','valor_a_faturar'):
            if key in item and item[key] not in (None,''):
                value += max(0,_float(item[key])); break
    return money(value)


def build_ledger(
    contracts: Mapping[str,Mapping[str,Any]],
    history: list[dict],
    pricing: dict,
    *,
    now_month: str,
    parse_billing_period: Callable[[dict],str | None],
    contract_values: Callable[[dict,dict],tuple[dict,dict]],
    item_reader: Callable[[dict],list[dict]],
) -> dict[str,Any]:
    """Retorna apuração somente de M1, M2 e M3 e as projeções de pagamento.

    Histórico encerrado permanece disponível para auditoria, mas não entra na
    visão de ciclos vigentes. A competência usada é a da fatura, nunca a de geração.
    """
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',now_month):
        raise ValueError('now_month inválido')
    history_index: dict[tuple[str,str],dict] = {}
    for h in history:
        period = parse_billing_period(h)
        c = norm(h.get('cliente'))
        if period and c:
            history_index.setdefault((c,period),h)

    positive: dict[str,list[str]] = defaultdict(list)
    billed_periods: dict[str,set[str]] = defaultdict(set)
    for (client,period),record in history_index.items():
        if billed_total(record,item_reader)>0 and period<=now_month:
            positive[client].append(period)
            billed_periods[client].add(period)
    for months in positive.values():months.sort()
    sales_by_month = sold_units_by_seller(contracts,billed_periods)
    possible_months = sorted(set(sales_by_month)|set(p for _,p in history_index)|{now_month},reverse=True)
    roster = {p:eligible_roster(contracts,p) for p in possible_months}

    rows: list[dict] = []
    clients: list[dict] = []
    for doc_id,contract in contracts.items():
        seller = str(contract.get('vendedor') or '').strip()
        client = str(contract.get('cliente') or doc_id).strip()
        signed = month_key(contract.get('ultima_atualizacao_termo'))
        if not seller or not signed:
            continue
        prices,qtys = contract_values(contract,pricing)
        discount,why=contract_discount(prices,qtys,contract.get('precos_tabela_produtos') or {})
        eligible=discount_is_eligible(discount)
        available = [p for p in positive.get(norm(client),[]) if p>=signed]
        first=available[0] if available else ''
        last=shift_month(first,2) if first else ''
        sellers=roster.get(signed) or eligible_roster(contracts,signed)
        seller_count=len(sellers)
        monthly_sales=sales_by_month.get(signed,{})
        units=int(monthly_sales.get(seller,0))
        attainment=float(installation_attainment(units,seller_count)) if seller_count>0 else 0.0
        target_pct=float(first_month_percent(attainment))
        contract_rows=[]
        expiry=month_key(contract.get('vencimento_contrato'))
        for i in range(3):
            period=shift_month(first,i) if first else ''
            invoice=history_index.get((norm(client),period)) if period else None
            billed=billed_total(invoice,item_reader)
            preliminary=bool(eligible and period and period<=now_month and billed>0 and (not expiry or period<=expiry))
            receipt=payment_confirmed(invoice,billed)
            activity=activity_confirmed(invoice)
            installation_proof=contract.get('instalacoes_confirmadas') is True
            release_rec=bool(preliminary and receipt is True and activity is True)
            release_first=bool(release_rec and i==0 and installation_proof)
            if not eligible: status='INELEGÍVEL — DESCONTO/TABELA'
            elif not first: status='AGUARDANDO M1'
            elif period>now_month: status='FUTURA'
            elif billed<=0: status='SEM FATURAMENTO'
            elif expiry and period>expiry: status='FORA DA VIGÊNCIA'
            elif release_rec: status='APURADA COM EVIDÊNCIAS'
            else: status='PROJEÇÃO — COMPROVAÇÃO PENDENTE'
            row={
                'Vendedor':seller,'Cliente':client,'Contrato':doc_id,
                'Data contrato':signed,'Competência da venda':signed,
                'Fatura':f'M{i+1}','Competência':period,'Fim da janela':last,
                'Desconto (%)':discount,'Referência':why,'Elegível':eligible,
                'Meta (%)':attainment,'Meta individual (un.)':unit_target(seller_count),
                'Vendedores considerados':seller_count,
                'Unidades vendidas pelo vendedor':units,
                'Valor faturado (R$)':billed,'Pagamento de fatura':('CONFIRMADO' if receipt is True else 'NÃO RECEBIDO' if receipt is False else 'SEM INFORMAÇÃO'),
                'Atividade':('CONFIRMADA' if activity is True else 'INATIVA' if activity is False else 'SEM INFORMAÇÃO'),
                'Status':status,'Apuração possível':preliminary,'Apto a pagar':release_rec,
                'Instalação comprovada':installation_proof,'Liberação M1':release_first,
                'Taxa M1 (%)':target_pct,'Bônus recorrente (%)':0.0,
                'Faixa recorrente':'Sem bônus',
                'Premiação M1 (R$)':0.0,'Premiação recorrente (R$)':0.0,'Premiação liberável (R$)':0.0,
            }
            rows.append(row);contract_rows.append(row)
        clients.append({
            'Vendedor':seller,'Cliente':client,'Data contrato':signed,
            'Competência da venda':signed,'M1':first or 'PENDENTE',
            'M2':shift_month(first,1) if first else '',
            'M3':last,'Fim da janela':last,
            'Status ciclo':(('ENCERRADO SEM M1' if shift_month(signed,3)<now_month else 'AGUARDANDO M1') if not first else
                            'ENCERRADO' if last<now_month else
                            'EM ANDAMENTO' if first<=now_month else 'PROGRAMADO'),
            'Elegibilidade':('ELEGÍVEL' if eligible else 'NÃO ELEGÍVEL'),
            'Desconto (%)':discount,'Meta (%)':attainment,
            'Premiação M1 (R$)':0.0,'Premiação recorrente (R$)':0.0,
            'Total apurado (R$)':0.0,'Total liberável (R$)':0.0,
            '_rows':contract_rows,
        })

    # Somar todos os contratos elegíveis DO VENDEDOR em cada competência,
    # exclusivamente dentro da primeira janela M1..M3 de cada contrato.
    monthly: dict[tuple[str,str],float] = defaultdict(float)
    for row in rows:
        if row['Apuração possível']:
            monthly[(norm(row['Vendedor']),row['Competência'])] += row['Valor faturado (R$)']
    for row in rows:
        if not row['Apuração possível']:
            continue
        total=monthly[(norm(row['Vendedor']),row['Competência'])]
        pct=float(recurring_percent(total))
        row['Bônus recorrente (%)']=pct
        row['Faixa recorrente']=band(total)
        row['Premiação recorrente (R$)']=percent_reward(row['Valor faturado (R$)'],pct)
        if row['Fatura']=='M1':
            row['Premiação M1 (R$)']=percent_reward(row['Valor faturado (R$)'],row['Taxa M1 (%)'])
        rec=row['Premiação recorrente (R$)'] if row['Apto a pagar'] else 0
        initial=row['Premiação M1 (R$)'] if row['Liberação M1'] else 0
        row['Premiação liberável (R$)']=money(initial+rec)

    for c in clients:
        related=c.pop('_rows')
        c['Premiação M1 (R$)']=money(sum(r['Premiação M1 (R$)'] for r in related))
        c['Premiação recorrente (R$)']=money(sum(r['Premiação recorrente (R$)'] for r in related))
        c['Total apurado (R$)']=money(c['Premiação M1 (R$)']+c['Premiação recorrente (R$)'])
        c['Total liberável (R$)']=money(sum(r['Premiação liberável (R$)'] for r in related))
    return {'rows':rows,'clients':clients,'sales':sales_by_month,'roster':roster,'months':possible_months,'history_index':history_index}


def due_items(rows: list[dict]) -> list[dict]:
    """Uma obrigação individual por componente (M1 + recorrência).

    O mesmo M1 pode gerar duas obrigações distintas e independente de pagamento.
    """
    entries=[]
    for r in rows:
        period=r['Competência']
        if not period or not r['Apuração possível']:
            continue
        for component,column in (('M1','Premiação M1 (R$)'),('RECORRENTE','Premiação recorrente (R$)')):
            amount=money(r.get(column,0))
            if amount<=0:continue
            entries.append({
                'ID':commission_id(r['Contrato'],r['Cliente'],period,component),
                'Vendedor':r['Vendedor'],'Cliente':r['Cliente'],'Contrato':r['Contrato'],
                'Competência':period,'Fatura':r['Fatura'],
                'Componente':component,'Valor previsto (R$)':amount,
                'Apto a pagar':r['Liberação M1'] if component=='M1' else r['Apto a pagar'],
            })
    return entries

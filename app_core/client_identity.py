"""Reconciliação conservadora de vendedores e documentos de clientes."""
from __future__ import annotations
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

def norm(value: object) -> str:
    s=unicodedata.normalize("NFKD",str(value or ""))
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).casefold().split())

def account_statuses(users: list[dict[str,Any]]) -> dict[str,bool]:
    """False para conta global inativa OU sem acesso financeiro.

    Se um nome/e-mail/username corresponder a contas conflitantes,
    a situação fica bloqueada, evitando incluir identidade desativada.
    """
    result:dict[str,bool]={}
    for user in users:
        active=bool(user.get('global_active')) and bool(user.get('finance_enabled'))
        aliases=(user.get('name'),user.get('username'),user.get('email'))
        for value in aliases:
            key=norm(value)
            if key:
                result[key]=result.get(key,True) and active
    return result

def blocked_contract_sellers(contracts:Mapping[str,Mapping[str,Any]],users:list[dict[str,Any]]) -> set[str]:
    statuses=account_statuses(users)
    return {norm(c.get('vendedor')) for c in contracts.values()
            if norm(c.get('vendedor')) in statuses and not statuses[norm(c.get('vendedor'))]}

def digits(value: object) -> str:
    if value is None or isinstance(value,bool):return ''
    raw=str(value).strip()
    if not raw or raw.casefold() in {'nan','none','null','nat'}:return ''
    if isinstance(value,float):
        if not value.is_integer() or abs(value)>2**53:return ''
        raw=str(int(value))
    if not re.fullmatch(r'[0-9.\/\-\s]+',raw):return ''
    return re.sub(r'\D','',raw)

def valid_document(value:object) -> bool:
    d=digits(value)
    if len(d) not in (11,14) or d==d[0]*len(d):return False
    if len(d)==11:
        v=[int(x) for x in d]
        first=(sum(v[i]*(10-i) for i in range(9))*10)%11
        second=(sum(v[i]*(11-i) for i in range(10))*10)%11
        return (first if first<10 else 0)==v[9] and (second if second<10 else 0)==v[10]
    def check(prefix: str, weights:list[int]) -> int:
        remain=sum(int(ch)*w for ch,w in zip(prefix,weights))%11
        return 0 if remain<2 else 11-remain
    return check(d[:12],[5,4,3,2,9,8,7,6,5,4,3,2])==int(d[12]) and check(d[:13],[6,5,4,3,2,9,8,7,6,5,4,3,2])==int(d[13])

def fmt_document(value:object) -> str:
    d=digits(value)
    if not valid_document(d):return ''
    if len(d)==11:return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'

def document_from_record(record:Mapping[str,Any]|None) -> str:
    if not isinstance(record,Mapping):return ''
    for key in ('cpf_cnpj','CPF/CNPJ','CPF / CNPJ','cnpj_cpf','cnpj','CNPJ','cpf','CPF','documento','Documento','numero_documento'):
        value=fmt_document(record.get(key))
        if value:return value
    return ''

def documents_by_client(contracts:Mapping[str,Mapping[str,Any]]) -> dict[str,str]:
    values:dict[str,set[str]]={}
    for doc_id,contract in contracts.items():
        document=document_from_record(contract)
        if not document:continue
        for label in (doc_id,contract.get('cliente')):
            key=norm(label)
            if key:values.setdefault(key,set()).add(document)
    # Em caso de CPF/CNPJ conflitando para mesmo nome, não escolher arbitrariamente.
    return {key:next(iter(docs)) if len(docs)==1 else '' for key,docs in values.items()}

def document_for_client(client:object,index:Mapping[str,str]) -> str:
    return index.get(norm(client),'')

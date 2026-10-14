"""Regras V5: vendedor ativo, meta por vendas e identificação documental."""
import unittest
from app_core.commission_v4 import build_ledger, eligible_roster
from app_core.client_identity import (blocked_contract_sellers, documents_by_client,
    document_for_client, fmt_document, valid_document,account_statuses)

class TestCommissionV5(unittest.TestCase):
    def contract(self,seller,name,qty):
        return {'cliente':name,'vendedor':seller,'ultima_atualizacao_termo':'2026-01-10',
                'vencimento_contrato':'2026-12-31','precos_produtos':{'R':100},
                'precos_tabela_produtos':{'R':100},'quantidades_produtos':{'R':qty}}
    def ledger(self,contracts,history,blocked=None):
        return build_ledger(contracts,history,{},now_month='2026-04',
            parse_billing_period=lambda x:x['period_key'],
            contract_values=lambda c,p:(c['precos_produtos'],c['quantidades_produtos']),
            item_reader=lambda r:[],blocked_sellers=blocked or set())
    def test_only_sellers_with_sale_divide_target(self):
        contracts={'a':self.contract('A','Cliente A',5),'b':self.contract('B','Cliente B',3),
                   'c':self.contract('C','Cliente C',2)}
        history=[{'cliente':'Cliente A','period_key':'2026-01','valor_total':1000},
                 {'cliente':'Cliente B','period_key':'2026-01','valor_total':1000}]
        data=self.ledger(contracts,history)
        self.assertEqual(data['roster']['2026-01'],['A','B'])
        a=next(x for x in data['rows'] if x['Vendedor']=='A')
        self.assertEqual(a['Meta individual (un.)'],12.5)
        self.assertEqual(a['Meta (%)'],40)
    def test_five_sellers_five_each(self):
        c={str(i):self.contract(f'Vendedor {i}',f'Cliente {i}',5) for i in range(5)}
        h=[{'cliente':f'Cliente {i}','period_key':'2026-01','valor_total':1000} for i in range(5)]
        ledger=self.ledger(c,h)
        self.assertEqual(len(ledger['roster']['2026-01']),5)
        self.assertTrue(all(r['Meta individual (un.)']==5 for r in ledger['rows']))
    def test_blocked_finance_and_global_and_unknown(self):
        users=[{'name':'Inativo','global_active':False,'finance_enabled':True},
               {'name':'Financeiro desligado','global_active':True,'finance_enabled':False},
               {'name':'Ativo','global_active':True,'finance_enabled':True}]
        contracts={str(i):self.contract(n,f'C{i}',1) for i,n in enumerate(('Inativo','Financeiro desligado','Ativo','Sem cadastro'))}
        blocked=blocked_contract_sellers(contracts,users)
        self.assertEqual(blocked,{'inativo','financeiro desligado'})
        hist=[{'cliente':f'C{i}','period_key':'2026-01','valor_total':100} for i in range(4)]
        data=self.ledger(contracts,hist,blocked)
        self.assertEqual(data['roster']['2026-01'],['Ativo','Sem cadastro'])
    def test_documents_and_collision(self):
        self.assertEqual(fmt_document('52998224725'),'529.982.247-25')
        self.assertEqual(fmt_document('11222333000181'),'11.222.333/0001-81')
        self.assertFalse(valid_document('00000000000'))
        self.assertEqual(fmt_document('99999'),'')
        c={'x':{'cliente':'Companhia','cpf_cnpj':'11222333000181'}}
        self.assertEqual(document_for_client('companhía',documents_by_client(c)),'11.222.333/0001-81')
        c['y']={'cliente':'Companhia','cpf_cnpj':'52998224725'}
        self.assertEqual(document_for_client('Companhia',documents_by_client(c)),'')

if __name__=='__main__':unittest.main()

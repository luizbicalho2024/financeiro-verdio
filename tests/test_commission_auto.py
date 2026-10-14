import unittest
from app_core.commission_auto import sold_units_by_seller, payment_confirmed, activity_confirmed, month_key

class TestCommissionAuto(unittest.TestCase):
    def test_aggregate_distinct_sellers(self):
        contracts = {
            '1': {'cliente':'Alpha', 'vendedor':'Ana', 'ultima_atualizacao_termo':'2026-10-01', 'quantidades_produtos': {'GPRS':10}},
            '2': {'cliente':'Beta', 'vendedor':'Ana', 'ultima_atualizacao_termo':'2026-10-02', 'quantidades_produtos': {'CAN':4}},
            '3': {'cliente':'Gamma', 'vendedor':'Bia', 'ultima_atualizacao_termo':'2026-10-03', 'quantidades_produtos': {'GPRS':11}},
            '4': {'cliente':'Delta', 'vendedor':'Bia', 'ultima_atualizacao_termo':'2026-10-04', 'quantidades_produtos': {'GPRS':100}},
        }
        result = sold_units_by_seller(contracts, {'alpha':{'2026-10'},'beta':{'2026-11'},'gamma':{'2026-10'}})
        self.assertEqual(result['2026-10'], {'Ana':14,'Bia':11})
        self.assertEqual(len(result['2026-10']), 2)

    def test_no_installation_inference(self):
        contracts = {'1':{'cliente':'Alpha','vendedor':'Ana','ultima_atualizacao_termo':'2026-10-01','competencia_instalacao':'2026-09','quantidades_produtos':{'GPRS':2}}}
        self.assertEqual(sold_units_by_seller(contracts, {'alpha':{'2026-11'}}), {'2026-10':{'Ana':2}})

    def test_not_count_without_billing(self):
        c={'1':{'cliente':'Alpha','vendedor':'Ana','ultima_atualizacao_termo':'2026-10-01','quantidades_produtos':{'GPRS':2}}}
        self.assertEqual(sold_units_by_seller(c, {}), {})

    def test_do_not_use_billing_before_sale(self):
        c={'1':{'cliente':'Alpha','vendedor':'Ana','ultima_atualizacao_termo':'2026-10-01','quantidades_produtos':{'GPRS':2}}}
        self.assertEqual(sold_units_by_seller(c, {'alpha':{'2026-09'}}), {})

    def test_payments_not_inferred(self):
        self.assertIsNone(payment_confirmed({'valor_total':9000, 'status':'closed'},9000))
        self.assertIsNone(payment_confirmed({'valor_total':9000},9000))
        self.assertFalse(payment_confirmed({'status_pagamento':'pendente'},9000))
        self.assertTrue(payment_confirmed({'valor_recebido':9000},9000))
        self.assertFalse(payment_confirmed({'valor_recebido':5000},9000))

    def test_activity_not_inferred(self):
        self.assertIsNone(activity_confirmed({'valor_total':100}))
        self.assertTrue(activity_confirmed({'atividade_confirmada':True}))
        self.assertFalse(activity_confirmed({'atividade_confirmada':False}))

    def test_month_parsing(self):
        self.assertEqual(month_key('15/10/2026'), '2026-10')
        self.assertEqual(month_key('2026-10-15'), '2026-10')
        self.assertEqual(month_key('2026-13-01'), '')

    def test_cancelled_and_bad_qty(self):
        c = {
            'a': {'cliente':'A','vendedor':'Ana','ultima_atualizacao_termo':'2026-10-01','quantidades_produtos':{'GPRS':2}, 'status_contrato':'cancelado'},
            'b': {'cliente':'B','vendedor':'Ana','ultima_atualizacao_termo':'2026-10-01','quantidades_produtos':{'GPRS':-1}},
        }
        self.assertEqual(sold_units_by_seller(c, {'a':{'2026-10'},'b':{'2026-10'}}), {})

if __name__ == '__main__':
    unittest.main()
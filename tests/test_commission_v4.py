"""Teste end-to-end de regras puras, sem MongoDB ou Streamlit."""
import unittest
from app_core.commission_v4 import (band, build_ledger, commission_id, commercial_totals, due_items, eligible_roster,period_label)


class TestCommissionV4(unittest.TestCase):
    def setUp(self):
        self.pricing={}
        self.contracts={}
        for n in range(1,6):
            seller=f"Vendedor {n}"
            self.contracts[f"contrato{n}"]={
                "cliente":f"Cliente {n}","vendedor":seller,
                "ultima_atualizacao_termo":"2026-01-12",
                "vencimento_contrato":"2026-12-31",
                "precos_produtos":{"Rastreador":100},
                "precos_tabela_produtos":{"Rastreador":100},
                "quantidades_produtos":{"Rastreador": n if n<5 else 5},
            }
        self.history=[{"cliente":"Cliente 5","period_key":f"2026-{m:02d}","valor_total":3000}
                      for m in (1,2,3,4,5)] + [
                      {"cliente":f"Cliente {n}","period_key":"2026-01","valor_total":100}
                      for n in (1,2,3,4)]

    def ledger(self,now="2026-04"):
        return build_ledger(self.contracts,self.history,{},now_month=now,
            parse_billing_period=lambda r:r.get("period_key"),
            contract_values=lambda c,p:(c["precos_produtos"],c["quantidades_produtos"]),
            item_reader=lambda r:[])

    def test_target_divisor_five_sellers_with_sales(self):
        data=self.ledger()
        self.assertEqual(len(data['roster']['2026-01']),5)
        self.assertEqual(data['rows'][0]['Meta individual (un.)'],5.0)
        self.assertEqual([r for r in data['rows'] if r['Vendedor']=='Vendedor 5'][0]['Meta (%)'],100)

    def test_only_first_three_calendar_billing_months(self):
        data=self.ledger()
        months=[r['Competência'] for r in data['rows'] if r['Cliente']=='Cliente 5']
        self.assertEqual(months,['2026-01','2026-02','2026-03'])
        self.assertNotIn('2026-04',months)
        self.assertEqual([c for c in data['clients'] if c['Cliente']=='Cliente 5'][0]['Status ciclo'],'ENCERRADO')

    def test_initial_and_recurring_separate_payments(self):
        data=self.ledger()
        rows=[r for r in data['rows'] if r['Cliente']=='Cliente 5']
        self.assertEqual(rows[0]['Premiação M1 (R$)'],450.0)
        self.assertEqual(rows[0]['Premiação recorrente (R$)'],60.0)
        entries=due_items(rows)
        self.assertEqual(len(entries),4) # M1 plus rec M1/M2/M3
        self.assertEqual(len({r['ID'] for r in entries}),4)

    def test_band(self):
        self.assertEqual([band(v) for v in (0,2000,2001,5000,5001,12000,12001)],
                          ['Sem bônus','Sem bônus','Prata','Prata','Ouro','Ouro','Diamante'])

    def test_contract_value(self):
        totals=commercial_totals(self.contracts,'2026-01')
        self.assertEqual(totals['Vendedor 5'],500.0)

    def test_period_label(self):
        self.assertEqual(period_label('2026-02'),'fev/2026')
        self.assertEqual(period_label('2026-12'),'dez/2026')

    def test_payment_id_stability(self):
        self.assertEqual(commission_id('c','cliente','2026-02','M1'),commission_id('c','cliente','2026-02','M1'))
        self.assertNotEqual(commission_id('c','cliente','2026-02','M1'),commission_id('c','cliente','2026-02','RECORRENTE'))

    def test_no_payable_without_receipt_evidence(self):
        data=self.ledger()
        records=[r for r in data['rows'] if r['Cliente']=='Cliente 5']
        self.assertTrue(all(r['Premiação liberável (R$)']==0 for r in records))


if __name__=='__main__':unittest.main()

# Histórico analítico de faturamento e churn

A atualização preserva duas visões complementares:

- `billing_history`: snapshot vigente por cliente/período, mantendo compatibilidade com as telas existentes.
- `billing_runs`: revisões imutáveis. Uma alteração real no faturamento do mesmo cliente/mês cria nova revisão; download repetido com os mesmos dados não cria duplicidade.

Também são mantidas:

- `billing_monthly_metrics`: projeção mensal usada pelo Comercial.
- `billing_terminal_snapshots`: visão vigente de terminal por mês.
- `billing_month_closures`: fechamento do processamento em lote.

A tela **Histórico de faturamento** possui uma ação administrativa para reconstruir a camada analítica a partir do `billing_history` já existente. Registros antigos sem item a item são preservados como `resumo_legado`; a receita continua utilizável, mas movimentos de terminal podem ser aproximados.

O fluxo principal passa a aceitar `.xls`, `.xlsx` e `.csv` no faturamento completo. O `.xls` requer `xlrd`, incluído em `requirements.txt`.

Para meses anteriores, o administrador também pode confirmar manualmente um **fechamento histórico** na mesma tela. Faça isso somente quando todos os clientes daquele período estiverem presentes no histórico; a marcação permite que o Simulador trate clientes que desapareceram no mês como churn total.

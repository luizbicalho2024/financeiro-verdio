# Política Meta 5 — V4, faixas e controle administrativo de pagamentos

## Apuração

- A meta corporativa de 25 unidades é rateada entre **todos os vendedores identificados com carteira contratual vigente na competência**, mesmo que não tenham vendido naquele mês. Ex.: cinco vendedores -> meta de cinco unidades cada. O cadastro atual não possui uma tabela de vínculos trabalhistas por mês, portanto o número de vendedores é **uma aproximação operacional**, derivada de contratos vigentes. Se houver colaboradores ativos sem carteira, será preciso integrar a fonte oficial para a apuração contratual exata.
- As vendas são atribuídas ao vendedor indicado no contrato e contabilizadas no mês de assinatura, condicionadas à existência de faturamento positivo posterior. Essa contagem é **venda**, não comprovação de instalação. A taxa M1 é **estimativa** enquanto não houver evidência de instalação.
- A faixa **comercial** (Sem bônus / Prata / Ouro / Diamante) mostrada na meta e consolidado mensal usa a soma de preço negociado × unidades de contratos elegíveis **assinados no mês**. O bônus **recorrente** usa separadamente o faturamento positivo agregado do vendedor **na competência**, limitado às três primeiras competências do respectivo contrato.
- Desconto de até 15% da tabela oficial é requisito de elegibilidade. As taxas M1 são 0%,10%,15%,20% conforme atingimento abaixo de 80%, de 80% a menos de 100%, de 100% a menos de 110%, e a partir de 110%. Recorrência: 0% até R$ 2.000; 2% acima de R$ 2.000 até R$ 5.000; 3% acima de R$ 5.000 até R$ 12.000; 4% acima de R$ 12.000.

## Janela temporal

- M1 = primeiro mês com faturamento positivo registrado depois da assinatura. M2 e M3 = dois meses calendários imediatamente seguintes. **M4 em diante nunca compõe a apuração desse contrato**, nem substitui meses sem faturamento.
- Por padrão, `/Comissao_Vendedores` exibe apenas ciclos em vigência e programados; encerrados migram para filtro de **Histórico encerrado**, sem descarte de valores já apurados. Contratos muito antigos sem M1 não ficam indefinidamente em ciclos ativos.
- O eixo do gráfico é a competência da fatura em **MM/AAAA**, e não a data em que o relatório foi gerado.

## Controle de pagamentos de comissão

- A página `/Controle_Pagamentos_Comissoes` mostra cada comissão prevista em registros distintos para **premiação M1** e **recorrência M1/M2/M3**.
- Um administrador pode marcar pagamentos já realizados; o sistema exige data e referência do pagamento, guarda responsável e evento de auditoria. Não transfere valores nem altera status de fatura. O estado é persistido na coleção MongoDB `commission_payments`.
- Uma obrigação identificada por contrato, cliente, competência e componente tem ID determinístico. Pagamento repetido não deve sobrescrever outro já marcado. O estorno exige justificativa e preserva os eventos anteriores.
- Se o contrato/faturamento sofrer ajuste e o valor recalculado diferir de um pagamento marcado, a página mantém o valor pago originalmente e emite alerta.
- A marcação PAGO **significa que o administrador registrou pagamento de comissão já realizado**, não que a fatura do cliente foi recebida ou que a instalação foi comprovada. Valores projetados e valores liberáveis são distintos.

## Limitações

- Um documento `client_contracts` atualmente armazena o contrato vigente do cliente, sem histórico de aditivos, trocas de vendedor ou múltiplos contratos simultâneos. Uma integração posterior deverá preservar a versão contratual por período para auditoria financeira integral.
- A fonte `billing_history` usa snapshots vigentes; a criação de novas revisões pode alterar a apuração projetada. O controle de pagamentos preserva snapshots de valores já marcados.
- O controle de recebimento de faturas requer integração financeira oficial; não se deve inferir liquidação a partir de `status="closed"` do relatório.

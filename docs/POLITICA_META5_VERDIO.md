# Política de premiação 7.5 — Meta 5: Bionio Frotas / Verdio

## Regra vigente

Contratos B2B emitidos, ativos, com cobrança e faturamento efetivo. Contratos cujo **desconto contratual ponderado por quantidade** sobre a tabela oficial seja **superior a 15%** são inelegíveis. Contratos sem fotografia de preços oficial, sem quantidades ou com preço negociado inválido ficam **pendentes de regularização**, sem apuração.

**A margem de contribuição não participa mais do critério de elegibilidade.** Ela permanece no cadastro contratual apenas para acompanhamento da rentabilidade. O snapshot de tabela é preservado no contrato para evitar recalcular contratos antigos com reajustes posteriores.

## Premiação não recorrente — somente M1

A meta corporativa é de 25 dispositivos instalados no mês, divididos pelo número de vendedores atuantes na mesma competência. A quantidade instalada por vendedor é um dado de conferência, e não uma inferência da quantidade contratada.

| Percentual de atingimento (instalações / meta individual) | Sobre o faturamento de M1 recebido |
| --- | ---: |
| Abaixo de 80% | 0% |
| De 80% até menos de 100% | 10% |
| De 100% até menos de 110% | 15% |
| A partir de 110% | 20% |

O documento original diz “acima de 110%”, mas deixa 110,00% sem classificação. Por continuidade das faixas, esta implementação interpreta **110,00% como 20%**. Confirmar com o RH/comercial se a leitura deve ser estritamente maior que 110%.

## Premiação recorrente — M1, M2 e M3

O faturamento mensal **recebido e validado**, proveniente de contratos elegíveis, é agregado por vendedor e competência. Usa-se uma taxa única sobre toda a base elegível daquela competência:

| Faturamento mensal elegível confirmado | Bônus |
| --- | ---: |
| Até R$ 2.000,00 | 0% |
| Acima de R$ 2.000,00 até R$ 5.000,00 | 2% |
| Acima de R$ 5.000,00 até R$ 12.000,00 | 3% |
| Acima de R$ 12.000,00 | 4% |

Somente as 3 competências consecutivas iniciadas no **primeiro faturamento positivo registrado a partir da competência de assinatura** são consideradas. Competências sem faturamento ou sem recebimento/atividade confirmados não geram bônus. M4 ou posteriores nunca são usados para substituir uma competência perdida. Se um contrato precisar de atribuição financeira diferente do cliente ou de uma competência de início distinta, requer conciliação adicional: o cadastro atual mantém um único contrato por cliente e não possui IDs de linha fatura-contrato.

## Fluxo operacional para apuração

1. Em **Contratos e Preços por Cliente**, cadastre vendedor, competência de instalação e quantidades/preços contratuais. Confira o snapshot de preços de tabela.
2. Em **Comissão de Vendedores**, selecione a competência da meta, registre o total de vendedores atuantes e as instalações efetivamente comprovadas de cada vendedor. Salve.
3. Em **Conferir recebimento e dispositivos ativos**, selecione a competência das faturas e marque **Recebido**, **Dispositivos ativos** e **Contrato ativo** somente após validar financeiro e operação. Salve.
4. Confira consolidados e planilha Excel. Um lançamento pendente ou sem referência de tabela não é liberado como comissão a pagar.

**Atenção**: os documentos `settings/commission_attainment_AAAA-MM` e `settings/commission_receipts_AAAA-MM` são lançamentos administrativos de conferência; **não são integrações automáticas** com o gateway de pagamentos, CRM, estoque ou SIGYO. A apuração gerada não liquida nem transfere comissões.

## Critérios que precisam de validação negocial

- A política apresenta um exemplo de 90% da meta por **faturamento** (R$ 9.000 / R$ 10.000), mas a tabela estabelece meta por **unidades instaladas**. Foi priorizada a tabela de dispositivos instalados.
- É necessário confirmar se a restrição de 15% se aplica ao **desconto total ponderado do contrato** ou a qualquer item isolado; atualmente aplica-se ao contrato como um todo.
- A premiação de M1 foi vinculada à competência de instalação informada no cadastro; se um contrato tiver ativações em múltiplos meses, será necessário granularizar as instalações por contrato/equipamento.
- `billing_history` não prova recebimento da fatura nem atividade do equipamento. A confirmação administrativa manual permanece obrigatória até integração com a fonte oficial dessas informações.
- Contratos legados sem snapshot oficial ou competência de instalação exigem regularização antes de premiação inicial.

## Exemplo do documento de política

Com R$ 9.000 de faturamento elegível confirmado em M1 e **90% de atingimento por unidades instaladas**, a premiação inicial é R$ 900,00. Na faixa Ouro, o bônus recorrente é R$ 270,00 por competência **em que persistirem R$ 9.000 recebidos e equipamentos ativos**, totalizando R$ 810,00 em M1–M3 se essas condições forem verdadeiras em todos os meses. Total máximo neste cenário: **R$ 1.710,00**.
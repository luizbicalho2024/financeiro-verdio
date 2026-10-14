# Política Meta 5 — apuração automática V3

## Fonte de dados

A tela de comissão utiliza `client_contracts` (vendedor, contrato, data de assinatura,
quantidades e preços) e `billing_history` (competência e valores faturados).
Não existe mais o formulário manual de instalações, de vendedores atuantes
ou a conferência manual por fatura.

## Cálculo automático da meta (aproximação comercial)

Cada contrato com vendedor, quantidades positivas e algum faturamento positivo
conta uma vez no **mês da assinatura**. As unidades vendidas são agregadas por
vendedor. O número de vendedores com vendas faturadas no mês define o divisor
`25 / vendedores com vendas`. A meta é uma aproximação operacional porque a
política exige **dispositivos instalados** e **vendedores atuantes**, e o cadastro
atual não demonstra instalação por equipamento nem a escala completa de vendedores.
Portanto, a taxa apurada é identificada como **estimada**. O valor não deve ser
tratado como comissão definitiva sem validação da correspondência com instalações.

O desconto contratual continua limitado a 15% sobre a tabela oficial (snapshot
mantido no cadastro). A premiação M1 estimada aplica 10%/15%/20% de acordo com
o atingimento da meta comercial calculada automaticamente. O bônus recorrente
estimado é 0%/2%/3%/4% de acordo com o faturamento elegível agregado por
vendedor e competência M1–M3. M4 não substitui meses anteriores.

## Faturamento não é recebimento

A apuração **prevista** é calculada automaticamente a partir do faturamento
positivo, sem qualquer confirmação manual por competência. Para diferenciar
previsão e valores liberáveis, o motor lê somente campos explícitos de liquidação
(`pagamento_confirmado`, `fatura_paga`, `recebimento_confirmado`,
`status_pagamento`, `situacao_pagamento`, `valor_recebido` ou `valor_pago`) e de
atividade (`dispositivos_ativos_confirmados` ou `atividade_confirmada`) quando
presentes no snapshot de `billing_history`. O campo genérico `status='closed'`
indica encerramento do relatório e nunca é usado como comprovação de pagamento.

Sem esses campos, a comissão permanece classificada como **projeção**, e o valor
liberável fica em zero. O sistema **não lança ou efetua pagamento** de comissões.

Os antigos documentos `settings/commission_attainment_AAAA-MM` e
`settings/commission_receipts_AAAA-MM` são preservados no banco, mas deixam
de ser lidos ou alterados pela página.

## Limitações remanescentes

- O cadastro de contratos guarda apenas o vínculo atual entre cliente e vendedor,
  sem histórico de mudança de vendedor ou divisão de comissão.
- Para aderência integral à política por **instalações**, integrar eventos de
  ativação/instalação e cadastro oficial de vendedores atuantes por competência.
- Para liberação financeira, integrar a origem oficial de faturas recebidas,
  atividade efetiva dos dispositivos e comprovação de instalação para o M1
  (campo `instalacoes_confirmadas=True` quando a integração demonstrar o fato).
  A tela não presume fatos que o MongoDB não comprova.

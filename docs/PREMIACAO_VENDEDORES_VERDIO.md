# Premiação de vendedores — política Verdio

## Etapa 1 — Contrato

- O vendedor vem do cadastro do contrato.
- A premiação de contrato é calculada por ativação/unidade contratada.
- Contratos com margem comprovada abaixo de 15% não são elegíveis.
- Contratos sem custo suficiente para comprovar a margem também ficam não elegíveis.
- A competência da premiação de contrato é o mês da data do termo/assinatura.

## Etapa 2 — Faturamento M1, M2 e M3

A janela é fixa nos três meses imediatamente posteriores ao mês da data do contrato.

Exemplo: contrato em 20/06/2026 -> M1 07/2026, M2 08/2026 e M3 09/2026.

Se uma competência não possuir faturamento, ela permanece sem faturamento e não é substituída por M4.

A premiação pode ser configurada como:

- faixas atuais por preço;
- percentual único sobre o valor realmente faturado;
- valor fixo por competência faturada.

## Status do ciclo

- `AGUARDANDO INÍCIO`: M1 ainda não começou.
- `EM ANDAMENTO`: a janela M1-M3 está em curso.
- `ENCERRADA (3/3)`: as três competências possuem faturamento processado.
- `ENCERRADA COM PENDÊNCIA`: a janela terminou e ao menos uma competência ficou sem faturamento.

O status de encerramento representa a conclusão da apuração M1-M3. O sistema ainda não mantém um controle separado de liquidação/pagamento da comissão.

## Consulta

A página permite filtrar por vendedor, cliente, status do ciclo, ano, mês e elegibilidade do contrato. As tabelas destacam situações elegíveis em verde, não elegíveis/pendentes em vermelho e situações em andamento/aguardando em amarelo.

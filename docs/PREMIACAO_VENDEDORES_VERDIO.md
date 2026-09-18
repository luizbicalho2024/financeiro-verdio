# Premiação de vendedores — política Verdio

## Fonte de dados

- Produtos, preços, custos e instalação: `simulador_db.pricing_config`, documento `global_prices`.
- Contratos: `client_contracts`.
- Faturamento real: `billing_history` e, quando necessário, `billing_runs/items`.
- Vendedor: campo `vendedor` do contrato. O mapeamento legado em `settings/seller_mappings` é apenas fallback.

## Regra implantada

A premiação possui duas etapas:

1. **Contrato**
   - mantém o valor configurável já existente como `bonus_ativacao`;
   - paga uma única vez por unidade contratada;
   - só é elegível quando a margem contratual comprovada for maior ou igual a 15%;
   - contratos sem custo cadastrado no Simulador ficam com margem pendente e não recebem a etapa de contrato.

2. **Três primeiras faturas**
   - usa exclusivamente as três primeiras competências faturadas após a assinatura/termo;
   - mantém as faixas anteriores: `<80%=0%`, `80% a <100%=2%`, `100% a <120%=15%`, `>=120%=30%`;
   - a faixa é calculada pelo valor unitário do contrato versus o preço-base do Simulador;
   - a comissão é aplicada ao valor efetivamente faturado, preservando o pró-rata.

A restrição de margem de 15% foi aplicada à etapa de contrato, conforme a regra informada. A etapa de faturamento continua seguindo as faixas já existentes.

## Compatibilidade

Contratos novos salvam o produto canônico do Simulador, quantidade, preço contratado, preço-base, custo e margem. Também continuam gravando `precos_por_tipo` para que as páginas de faturamento existentes permaneçam compatíveis.

Contratos antigos são aceitos: o sistema tenta mapear `GPRS`, `SATELITE`, `CAMERA`, `CAN`, `RFID` e `RADIO` para os produtos atuais e usa a primeira fatura como fallback de mix quando a quantidade contratada não existe.

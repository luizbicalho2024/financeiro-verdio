# Importação de estoque e carga histórica de faturamento

## Gestão de Estoque

A página `Gestao_Estoque` aceita `.xls`, `.xlsx` e `.csv`.

O parser localiza automaticamente o cabeçalho e suporta a exportação do sistema
atual com campos como Modelo, Gateway, Equipamento, P/ Entrada, Status,
Tipo Equipamento e Situação.

`Equipamento` é normalizado para `Nº Equipamento`.

O campo `Tipo Equipamento` de origem é preservado como
`Tipo Equipamento Origem`. Ele não é convertido cegamente para a classificação
financeira, pois valores como `Comum` não indicam se o equipamento é GPRS ou
satelital.

Antes da gravação, a interface exibe uma tabela por modelo para classificar
GPRS, SATELITE, CAMERA ou RADIO.

## Faturamento Verdio Completo

O uploader aceita múltiplos arquivos simultaneamente.

1. Cada arquivo é lido separadamente.
2. O período é identificado no próprio relatório.
3. Arquivos do mesmo período são agrupados.
4. Duplicidades por cliente/terminal/equipamento são consolidadas.
5. Cada período possui revisão própria.
6. Cada período pode ser salvo isoladamente.
7. A ação de carga histórica salva todos os meses processados.

O fechamento mensal continua ocorrendo individualmente por período, preservando
a consistência das métricas de churn.

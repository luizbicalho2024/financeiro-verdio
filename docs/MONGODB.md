# Financeiro Verdio em MongoDB

O Financeiro Verdio não depende mais de Firebase Authentication nem Firestore.

## Banco

- Cluster: o mesmo MongoDB Atlas já utilizado pelo ecossistema, salvo configuração diferente.
- Database do Financeiro: `financeiro_verdio` por padrão.
- Database do Simulador: permanece independente (`simulador_db`).

## Coleções principais

- `users`
- `system_logs`
- `trackers`
- `settings`
- `client_contracts`
- `regras_parceiros`
- `terminais_parceiros`
- `billing_history`
- `billing_runs`
- `billing_runs__items`
- `billing_terminal_snapshots`
- `billing_monthly_metrics`
- `billing_month_closures`

## Autenticação

As senhas são armazenadas com PBKDF2-HMAC-SHA256, salt individual e 600.000 iterações.
O primeiro administrador é criado automaticamente quando `users` estiver vazia e os Secrets
`FINANCEIRO_ADMIN_EMAIL` e `FINANCEIRO_ADMIN_PASSWORD` estiverem configurados.

Não há rotina de importação do Firebase. Os faturamentos devem ser enviados novamente por planilha.

# Identidade compartilhada entre Simulador e Financeiro

## Fonte única de usuários

A coleção oficial de identidade é:

`simulador_db.users`

O Financeiro não mantém senhas nem usuários duplicados.

## Dados financeiros

Os dados funcionais permanecem no banco:

`financeiro_verdio`

Incluindo histórico de faturamento, contratos, configurações, estoque,
analytics de churn e fechamentos mensais.

## Autorização por aplicação

Cada usuário pode possuir:

```json
{
  "apps": {
    "simulador": {
      "enabled": true,
      "role": "admin"
    },
    "financeiro": {
      "enabled": true,
      "role": "admin"
    }
  }
}
```

Para usuários existentes, a implantação cria os campos automaticamente:

- `admin` global: Financeiro habilitado como `admin`;
- demais perfis: Financeiro desabilitado inicialmente;
- nenhum hash de senha é alterado.

## Senhas

O Financeiro valida diretamente o `hashed_password` bcrypt criado pelo
Simulador. Alterar a senha no Simulador altera imediatamente a credencial
válida para o Financeiro.

## Bloqueio e exclusão

Se `active=false` ou o usuário for removido no Simulador, o acesso ao
Financeiro também deixa de funcionar.

## Administração

O Financeiro possui uma tela de autorização que controla somente:

- acesso ao Financeiro;
- perfil `Usuário` ou `Admin` no Financeiro.

Cadastro, senha, nome, e-mail, papel global e exclusão permanecem sob
responsabilidade do Simulador.

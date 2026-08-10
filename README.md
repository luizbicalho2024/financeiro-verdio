# Financeiro Verdio

Plataforma Streamlit para faturamento, histórico financeiro, contratos, comissões, estoque, relatórios e controles administrativos do Verdio.

## Versão corporativa

A atualização corporativa centraliza a interface e a segurança de navegação em `app_core/` e adiciona identidade visual configurável pelo administrador.

Principais recursos:

- login via Firebase Authentication;
- perfis `Usuário` e `Admin`;
- duas logomarcas independentes: login/conteúdo e sidebar;
- cores do sistema configuráveis no Firestore;
- sidebar única com navegação organizada por perfil;
- bordas visíveis em inputs e componentes de formulário;
- padrão visual consistente para cartões, tabelas, métricas, formulários e gráficos;
- home com acessos rápidos e faturamentos recentes;
- inventário com gravação em lotes seguros para Firestore;
- cache com invalidação específica após alterações;
- logs e históricos com limites de leitura;
- dependências declaradas e compatíveis com Streamlit Cloud;
- exemplo de `secrets.toml` sem credenciais reais.

## Identidade visual

Acesse como administrador:

`Identidade visual`

As configurações são salvas em:

`settings / branding`

O sistema aceita:

- nome e subtítulo;
- texto do rodapé;
- cores de marca, fundo, cartões, textos, bordas e sidebar;
- logo principal;
- logo exclusiva da sidebar.

As imagens são otimizadas antes da gravação para reduzir o risco de ultrapassar o limite de documento do Firestore.

## Secrets

O projeto requer duas seções no Streamlit Cloud:

- `[service_account]`: credencial Firebase Admin;
- `[firebase]`: configuração Web do Firebase usada pelo Pyrebase.

Use `.streamlit/secrets.example.toml` apenas como referência. Nunca versionar chaves reais.

## Execução local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run 1_Home.py
```

Crie `.streamlit/secrets.toml` localmente com as credenciais do ambiente de desenvolvimento.

## Publicação

O Streamlit Cloud pode apontar para:

- branch: `main`;
- arquivo principal: `1_Home.py`.

Após mudanças em `requirements.txt`, execute **Reboot app** para forçar a reconstrução do ambiente quando necessário.

## Estrutura

```text
1_Home.py
app_core/
  auth.py
  branding.py
  settings.py
  ui.py
pages/
  ...
  90_Identidade_Visual.py
firebase_config.py
auth_functions.py
user_management_db.py
requirements.txt
```

## Compatibilidade

A página `pages/6_Faturamento_Verdio.py` foi mantida por compatibilidade. A navegação corporativa destaca `pages/5_Faturamento_Verdio_Completo.py` como fluxo principal.

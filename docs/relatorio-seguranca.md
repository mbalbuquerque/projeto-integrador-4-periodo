# Relatório de segurança (verificações automáticas)

Data: 16/11/2026. Fonte: workflow `Segurança` (`.github/workflows/seguranca.yml`), que roda sob
demanda, toda segunda-feira e quando as dependências mudam. O relatório do ZAP fica como artefato
`relatorio-zap-api` de cada execução.

## Resultado

| Verificação | Alvo | Resultado |
|---|---|---|
| `pip-audit` | `cloud/function/requirements.txt` | Sem vulnerabilidade conhecida |
| `npm audit --omit=dev --audit-level=high` | Painel (`Front-End-pi`) | Sem alerta alto |
| ZAP baseline (passivo) | `https://func-coldtrack-7319.azurewebsites.net/api/docs` | **0 alertas altos**, 12 avisos, 56 verificações sem apontamento |

A varredura é passiva: observa as respostas, não ataca. Ela não substitui um teste de invasão nem a
verificação de autorização por objeto, que está nos testes automatizados (`test_acesso.py`,
`test_seguranca.py`).

## Avisos do ZAP e o que foi feito

| Aviso | Onde aparece | Situação |
|---|---|---|
| Strict-Transport-Security ausente | `/api/docs` | Corrigido: a API envia o cabeçalho (confirmado na segunda execução) |
| Permissions-Policy ausente | `/api/docs` | Corrigido (confirmado na segunda execução) |
| Cache-Control / conteúdo armazenável | `/api/docs` | Corrigido para `no-store` em 16/11; confirmar na próxima execução |
| Cabeçalhos de segurança nas respostas JSON | Todas as rotas da API | Corrigido: `X-Content-Type-Options`, `Cache-Control: no-store`, `Strict-Transport-Security`, `Referrer-Policy` |
| CSP, X-Content-Type-Options, anti-clickjacking, SRI, scripts de outro domínio, Permissions-Policy | `/` | Não é nosso: é a página inicial padrão do Azure Functions |
| HSTS e cache | `/api`, `/robots.txt`, `/sitemap.xml` (404) | Não é nosso: respostas 404 geradas pela plataforma |
| CSP: `style-src 'unsafe-inline'` | `/api/docs` | Aceito: o Swagger UI usa estilos inline; os scripts seguem restritos por hash e por domínio |
| Cross-Origin-Embedder-Policy ausente | `/` e `/api/docs` | Aceito: `require-corp` bloquearia o carregamento do Swagger pelo CDN |
| Modern Web Application | `/api/docs` | Informativo |

## Próximos passos

- Rodar de novo o workflow e confirmar que os avisos de cache em `/api/docs` saíram.
- Fazer uma varredura ativa (ZAP full scan) com um usuário de teste, só em ambiente de teste.
- Cobrir o painel publicado (site estático no Azure Storage) numa segunda varredura.

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
| ZAP API scan (ativo, autenticado) | Contêiner da API com emulador do Cosmos, nunca produção (workflow `Compose e ZAP`) | **0 alertas altos**, 1 médio, 6 baixos, 4 informativos; 117 verificações sem apontamento |

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
- Cobrir o painel publicado (site estático no Azure Storage) numa segunda varredura.

## Varredura ativa (ZAP API scan) em ambiente de teste

Data: 16/11/2026. Alvo: a API em contêiner (`infra/docker-compose.yml`) com o emulador do Cosmos
DB, dentro do runner do GitHub Actions. Nunca contra produção. O `zap-api-scan.py` lê o
`openapi.json` (22 caminhos), roda a varredura ativa (injeção, XSS, travessia de caminho,
execução remota etc.) e envia o token de um gestor de teste, para alcançar também as rotas
protegidas. O job falha se houver alerta alto. Relatórios (`relatorio-zap-ativo.html/.json/.md`)
no artefato `compose-e-zap`.

Contagem da execução final do PR: **0 altos, 1 médio, 6 baixos, 4 informativos**, 117 verificações
sem apontamento.

| Risco | Alerta | Triagem |
|---|---|---|
| Médio | CSP: `style-src 'unsafe-inline'` em `/api/docs` | Aceito: o Swagger UI usa estilos inline; scripts seguem restritos por hash e domínio (já registrado acima) |
| Baixo | Resposta de erro do servidor (1 ocorrência: `POST /api/chat` com 503) | Esperado no teste: o contêiner não tem Azure OpenAI, e a rota devolve 503 por desenho |
| Baixo | Cross-Origin-Resource-Policy ausente (5), Cross-Origin-Opener-Policy (1) e Embedder-Policy (1) | Aceito: a API é chamada por `fetch` com CORS, que a CORP não afeta; COEP `require-corp` quebraria o Swagger pelo CDN. Reavaliar se a API servir imagem ou arquivo |
| Baixo | Timestamp Disclosure - Unix em `/api/openapi.json` | Falso positivo: números do documento OpenAPI que parecem data; a spec é pública |
| Baixo | Content-Type inesperado em `/`, `/api/docs` e `/api/docs/` (4) | Aceito: o ZAP esperava JSON da spec; essas rotas devolvem HTML (página inicial da plataforma e Swagger) |
| Informativo | 70 respostas 4xx, sessão, conteúdo não armazenável, aplicação moderna | Esperado: são as recusas de autenticação e de validação que a varredura provoca |

**Correção feita por causa da varredura.** A primeira execução reportou 3 respostas 500. Duas eram
um defeito real: `POST /api/login` e `POST /api/empresas` com e-mail contendo `/`, `\`, `?` ou `#`
(ex.: `http://www.google.com/`) causavam exceção no SDK do Cosmos, porque o e-mail é o `id` do
documento e esses caracteres não são aceitos em `id`. A validação de e-mail passou a recusar esses
caracteres (cadastro responde 400) e o login trata o valor como conta inexistente (401, igual a
qualquer credencial errada). Teste de regressão em `test_rotas.py`. Na execução final restou só o
503 esperado do `/api/chat`.

Limites da varredura: sem Azure OpenAI no contêiner, `/api/chat` e `/api/assistente` não são
exercitados de ponta a ponta; o painel (site estático) não foi coberto; a autorização por objeto
continua nos testes automatizados. A varredura envia o mesmo token a todas as rotas, e as rotas
`/api/sair` e `/api/senha` invalidam a sessão durante o scan, o que pode reduzir a profundidade das
requisições seguintes.

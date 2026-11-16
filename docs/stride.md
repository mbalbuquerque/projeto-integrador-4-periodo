# Modelo de ameaças (STRIDE)

Fluxo principal: sensor (ESP32-C3) → API (Azure Functions) → Cosmos DB → painel web (e PWA).
Os controles citados estão descritos em [`seguranca.md`](seguranca.md). Ameaças sem controle
completo aparecem em "Risco residual".

## Fronteiras de confiança

1. Placa e sensor (campo, fisicamente acessíveis).
2. Rede aberta entre placa/navegador e a API (HTTPS).
3. Azure: Function App, Cosmos DB, Azure OpenAI (identidade gerenciada).
4. Navegador do usuário.

## Ameaças por categoria

| Categoria | Ameaça | Componente | Controle | Risco residual |
|---|---|---|---|---|
| Spoofing | Terceiro envia leituras falsas fingindo ser um sensor | `POST /telemetria` | Chave aleatória de 32 bytes por sensor; o banco guarda só o SHA-256; a chave só vale para o próprio `deviceId` | Chave extraída da flash da placa permite forjar aquele sensor |
| Spoofing | Roubo ou adivinhação de credencial de usuário | `POST /login` | Senha com scrypt e sal; mesma resposta 401 para e-mail inexistente, senha errada e conta em espera; espera crescente e limite por IP | Atacante com muitos IPs ainda pode provocar espera na conta (até 15 min) |
| Tampering | Alterar leitura já gravada | Cosmos DB | Gravação só com `create`, nunca `upsert`; mesmo horário com outros valores recusado (409) | Quem tem acesso administrativo ao Cosmos continua podendo alterar |
| Tampering | Injeção em consulta | API | Consultas parametrizadas; entradas validadas pelo contrato | — |
| Tampering | Instrução maliciosa em dado cadastrado, lida pelo assistente de IA | `/assistente` | Dados marcados como não confiáveis; prompt proíbe seguir instruções e escrever links; links externos removidos da resposta | Modelo de linguagem não oferece garantia total |
| Repudiation | Usuário nega uma ação | API e painel | Logs sem senha nem token; e-mail mascarado; tela de auditoria | Logs centralizados e retenção definidos só na entrega final |
| Information disclosure | Usuário vê dados de outra empresa | Todas as rotas | `empresaId` do token em toda consulta; item de outra empresa responde 404; ids `<empresa>~<código>` | `409` ao cadastrar e-mail ou `deviceId` revela que já existe |
| Information disclosure | Interceptação do tráfego | Placa → API, navegador → API | Somente HTTPS, TLS mínimo 1.2 na Function, Storage e Cosmos; CORS só para o painel | Token no `localStorage` exposto a XSS; mitigado por escape do React e CSP em `<meta>` |
| Information disclosure | Segredo no repositório | Git | Nenhum segredo no histórico; `secrets.h` e `local.settings.json` fora do Git; deploy por OIDC | Connection string e `JWT_SECRET` em app settings, e não em Key Vault |
| Denial of service | Excesso de chamadas | `/login`, `/chat`, `/assistente`, `/telemetria` | Limites por IP, por minuto e por dia, no Cosmos (somados entre instâncias) | `/telemetria` lê o banco antes de conferir a chave; chamadas em massa gastam leituras |
| Denial of service | Rede ou nuvem fora | Placa | Fila em flash com até 500 leituras e reenvio ao reconectar | Sem backup do banco ainda (R8) |
| Elevation of privilege | Perfil sem permissão acessa rota restrita | API | Perfil relido do banco a cada chamada; perfil ausente → 403; campos de perfil e empresa ignorados no corpo da requisição | — |
| Elevation of privilege | Token roubado continua válido | Sessão | Versão de sessão no token; trocar senha, `POST /sair` ou remover usuário invalida na hora | — |

## Itens da entrega final

Varredura ZAP sem alerta alto, verificação de dependências, ficha OWASP IoT/API e seção de
LGPD estão em [`PLANO_ACAO.md`](../PLANO_ACAO.md).

# Segurança do ColdTrack: Projeto Final

## 1. Identificação

- **Projeto:** ColdTrack (monitoramento de temperatura de carga refrigerada).
- **Código de missão:** CÓDIGO-DE-MISSÃO a preencher (6 caracteres enviados pelo professor).
- **Integrantes:**

| Nome | Usuário no GitHub |
|---|---|
| Enzo Antônio | Benzo171 |
| Everson | Everson9 |
| Emmanuel Luís | MrLlouis |
| Gabriel Eduardo | gabrielfranca42 |
| José Allamberg | berg2132 |
| Marcelo Barbosa | mbalbuquerque |

## 2. O projeto

Placa **ESP32-C3** com sensor **DHT11** dentro do baú refrigerado. A placa mede temperatura e
umidade e envia cada leitura por HTTPS (JSON) para a API em **Azure Functions**
(`POST /api/telemetria`), autenticada pelo cabeçalho `x-device-key` (chave aleatória por sensor;
o banco guarda só o SHA-256). As leituras ficam no **Cosmos DB** (container `leituras`,
particionado por `deviceId`) e aparecem no painel web em **React + Vite** (também PWA), servido
como site estático do Azure Storage. Cada empresa só enxerga os próprios sensores, veículos,
viagens e usuários: o token leva a empresa e toda consulta filtra por ela.

- **Back-end:** Python 3.11, Azure Functions (gatilhos HTTP), Cosmos DB, JWT HS256 de 8 h, senha com scrypt.
- **Front-end:** React + Vite, PWA, Web Push; chama a API com `Authorization: Bearer <token>`.
- **API em produção:** `https://func-coldtrack-7319.azurewebsites.net/api`.

Documentos de base: [`modelo-ameacas.md`](modelo-ameacas.md), [`uso-de-ia.md`](uso-de-ia.md),
[`docs/stride.md`](../docs/stride.md) e [`docs/seguranca.md`](../docs/seguranca.md).

## 3. Controle 1: 2FA com TOTP no login (#113)

- **Ameaça:** senha vazada de um gestor dá acesso a tudo da empresa (Spoofing).
- **Controle:** segundo passo no login com o código de 6 dígitos do app autenticador (TOTP,
  RFC 6238, biblioteca `pyotp==2.9.0`) ou um código de recuperação de uso único.
  - `POST /api/login` com a senha certa e 2FA ligado devolve `{"exige2fa": true, "desafio": "..."}`
    e **nenhum token**. O desafio é um JWT de 5 min com a marca `2fa`; as rotas normais o recusam
    (`ler_token` em [`seguranca.py`](../cloud/function/seguranca.py) devolve `None`).
  - `POST /api/login/2fa` com `{desafio, codigo}` ou `{desafio, recuperacao}` devolve `{token, usuario}`.
    Código errado, vencido ou já usado e desafio ausente ou vencido: `401 {"erros": [...]}`, sempre
    com a mesma mensagem, e o log `2fa bloqueado [<MISSAO_CODIGO>]`. Tentativas demais: `429`
    (10 erros por IP e 5 por conta a cada 5 min; o limite por conta segura quem troca de IP).
  - `POST /api/2fa/iniciar` devolve `{"uri": "otpauth://..."}` e guarda o segredo novo em
    `totpSecretTemp`. Com o 2FA já ligado (celular novo), o segredo em uso continua valendo até o
    `POST /api/2fa/ativar` confirmar o novo com um código; só então troca.
  - `POST /api/2fa/ativar` devolve os 10 códigos de recuperação (8 caracteres) **só nessa resposta**.
  - `POST /api/2fa/desativar` exige a senha e um código (TOTP ou de recuperação) e responde `204`.
  - `GET /api/eu` e o `usuario` do login trazem `totpAtivo` (a tela mostra "Ativar" ou "Desativar").
  - Campos gravados no usuário (Cosmos, container `usuarios`): `totpAtivo`, `totpSecret`,
    `totpSecretTemp` (provisório), `totpContadorUsado` (último passo de 30 s aceito: o mesmo código
    não entra duas vezes) e `recoveryCodes` (lista de hashes; o código usado sai da lista).
  - Os códigos de recuperação são guardados com **scrypt com sal** (a mesma função das senhas),
    em vez do SHA-256 sugerido na issue: quem ler o banco não consegue testar códigos em massa.
  - Código: [`cloud/function/seguranca.py`](../cloud/function/seguranca.py) (TOTP, códigos,
    desafio, logs) e [`cloud/function/function_app.py`](../cloud/function/function_app.py)
    (`login`, `login_2fa`, `totp_iniciar`, `totp_ativar`, `totp_desativar`). Telas no repositório
    `Front-End-pi`: `src/pages/Configuracoes/DoisFatores.jsx`, `src/pages/Login/Login.jsx` e
    `src/lib/doisFatores.js`.
- **Como testar:**
  ```bash
  cd cloud/function
  pip install -r requirements.txt -r requirements-dev.txt
  python -m unittest test_2fa test_2fa_rotas -v
  ```
  [`test_2fa.py`](../cloud/function/test_2fa.py) testa o módulo (código certo, errado, de 2 min
  atrás, reuso, códigos de recuperação, desafio vencido ou adulterado);
  [`test_2fa_rotas.py`](../cloud/function/test_2fa_rotas.py) tem um teste para cada linha do
  critério de aceite da #113 (senha sem código não dá token; código errado ou vencido dá 401 com o
  log; código válido dá token; o mesmo código de novo dá 401; código de recuperação entra uma vez
  só; 429; desafio não serve como token; usuário sem 2FA entra como antes).

  Contra a API em produção, com a mesma conta antes e depois de ligar o 2FA:
  ```bash
  pip install pyotp==2.9.0   # ou o requirements.txt da API
  MISSAO_CODIGO=<codigo> bash seguranca/testes/2fa_antes_depois.sh
  ```
  [`testes/2fa_antes_depois.sh`](testes/2fa_antes_depois.sh) cria uma empresa temporária
  (e-mail fictício `@exemplo.com` e senha aleatória gerada no script), liga o 2FA pelas rotas
  `/2fa/iniciar` e `/2fa/ativar` e apaga a empresa no fim com `DELETE /empresa`, mesmo se parar
  no meio. Cada passo sai com o status HTTP esperado e o obtido; senha, token, desafio e segredo
  TOTP não aparecem. `API_URL` troca o alvo. Cuidado: `POST /empresas` aceita 5 cadastros por
  hora por IP.
- **Resultado antes/depois:** no log
  [`evidencias/SEM-CODIGO-2fa-antes-depois.log`](evidencias/SEM-CODIGO-2fa-antes-depois.log),
  gerado pelo script em produção (21 passos, APROVADO):
  - **antes** (2FA desligado): `POST /login` só com a senha devolve `200` com token e `GET /eu`
    abre com ele;
  - **depois** (mesma conta, 2FA ligado): `POST /login` só com a senha devolve `200` sem token,
    com `exige2fa` e o desafio; o desafio usado como token em `GET /eu` dá `401`;
    `POST /login/2fa` com código errado dá `401` e com o código certo devolve o token.

  Prints e vídeo da tela em [`evidencias/`](evidencias/), com o código de missão no nome
  (roteiro em [`evidencias/LEIAME.md`](evidencias/LEIAME.md)). O log sai com `SEM-CODIGO` no
  nome enquanto o código de missão não chega; depois, roda-se o script de novo com
  `MISSAO_CODIGO=<codigo>`.
- **Limitações:**
  - O 2FA é opcional: cada usuário liga o seu em Configurações; a API não obriga nenhum perfil.
  - Quem perde o celular e os códigos de recuperação não tem como entrar sozinho; precisa de ajuda
    de quem tem acesso ao banco.
  - O reuso do mesmo código em duas chamadas simultâneas é barrado por uma gravação condicional
    (etag do Cosmos): só a primeira grava o passo usado; a segunda recebe `401`. Isso vale para o
    login; no `ativar` e no `desativar` (que já exigem token e, no desativar, a senha) a gravação
    não é condicional.
  - O segredo TOTP fica no banco em texto (o servidor precisa dele para calcular o código); quem
    tiver acesso de leitura ao Cosmos pode gerar códigos.
  - O relógio do servidor precisa estar certo; a janela aceita o passo anterior e o seguinte (±30 s).

## 4. Controle 2: proteção contra IDOR com verificação de dono (#114)

- **Ameaça:** usuário da empresa A troca o ID na URL e lê ou altera dados da empresa B.
- **Controle:** função central `exigir_dono(nome, item_id, usuario, rota)` em
  [`function_app.py`](../cloud/function/function_app.py). O id vem da URL; o dono vem sempre do
  token (usuário relido do banco por `autorizar`), nunca do corpo. Item inexistente e item de outra
  empresa recebem a **mesma** resposta (`404`) e o log
  `idor bloqueado [<MISSAO_CODIGO>] rota=... usuario=a***@... alvo=...` (e-mail mascarado).
  Rotas que recebem ID e usam a função:
  - `GET /api/leituras?deviceId=` e `GET /api/predict/sensor?deviceId=`;
  - `PUT` e `DELETE /api/dispositivos/{id}`;
  - `GET`, `PUT` e `DELETE /api/veiculos/{id}` e `/api/viagens/{id}`;
  - `PUT` e `DELETE /api/usuarios/{id}`.

  `GET /api/motorista` não recebe ID: o veículo vem do cadastro do motorista no banco.
- **Como testar:**
  ```bash
  cd cloud/function
  python -m unittest test_idor -v
  ```
  [`test_idor.py`](../cloud/function/test_idor.py) cria duas empresas e testa, para cada rota acima,
  que A com o ID de B recebe 404 e deixa `idor bloqueado [` no log, e que B continua usando o
  próprio. Tentativas de contorno: `deviceId` em maiúsculas, `empresaId` de B no corpo do `PUT`,
  `deviceId` repetido na URL, token de usuário apagado e id com o prefixo de outra empresa.
- **Resultado antes/depois:** [`testes/idor_antes_depois.sh`](testes/idor_antes_depois.sh) roda o
  mesmo teste no commit `d44b301` (antes da verificação de dono) e no commit atual:
  ```bash
  MISSAO_CODIGO=<codigo> bash seguranca/testes/idor_antes_depois.sh
  ```
  No antes os testes de bloqueio **falham** (A lê as leituras do sensor de B e apaga veículo,
  viagem e usuário de B: HTTP 200 e 204); no depois passam. Saídas em
  [`evidencias/SEM-CODIGO-idor-antes.txt`](evidencias/SEM-CODIGO-idor-antes.txt) e
  [`evidencias/SEM-CODIGO-idor-depois.txt`](evidencias/SEM-CODIGO-idor-depois.txt).
  Ajustes para rodar no commit antigo: o script copia `test_idor.py` e `test_falsos.py` (o Cosmos
  falso, que não existia) para uma cópia temporária do `d44b301`; lá roda só a classe
  `TestAtaqueEntreEmpresas`, e as rotas que ainda não existiam (`dispositivos`, `predict/sensor`)
  aparecem como "skipped". O teste grava os cadastros no formato de id de cada versão
  (`<empresa>~<código>` depois do commit `19ace8e`).
  Os arquivos saem com `SEM-CODIGO` no nome enquanto o código de missão não chega; quando chegar,
  roda-se o script de novo com `MISSAO_CODIGO=<codigo>` (ou renomeiam-se os dois arquivos com o
  código no lugar de `SEM-CODIGO`).
- **Limitações:**
  - Rota nova que recebe ID precisa chamar `exigir_dono`; só os testes cobram isso.
  - `GET /api/veiculos`, `/viagens`, `/dispositivos` e `/usuarios` sem ID não usam a função: listam
    só a empresa do token pelo filtro da consulta.
  - O log não distingue "não existe" de "é de outra empresa" (os dois viram `idor bloqueado`).

## 5. Log de bloqueios

Os dois controles registram o bloqueio com o código de missão (app setting `MISSAO_CODIGO`, nunca no código): `2fa bloqueado [...]` e `idor bloqueado [...]`. Enquanto a app setting não existir, os logs saem com `[SEM-CODIGO]`. Consulta no Log Analytics em [`evidencias/LEIAME.md`](evidencias/LEIAME.md).

## 6. Segredos no histórico

Verificação feita em 23/11/2026 nos 292 commits de todas as branches: nenhum segredo real encontrado (chaves de conta, tokens, chave privada, senhas literais). Arquivos `secrets.h`, `local.settings.json` e `.env` nunca entraram no Git; só os `*.example`.

## 7. Evidências

Prints, logs e vídeos de até 90 s, todos com o código de missão no nome, em [`evidencias/`](evidencias/). Roteiro de captura em [`evidencias/LEIAME.md`](evidencias/LEIAME.md). Os arquivos `SEM-CODIGO-idor-antes.txt` e `SEM-CODIGO-idor-depois.txt` ganham o código de missão no nome quando ele chegar (item 4).

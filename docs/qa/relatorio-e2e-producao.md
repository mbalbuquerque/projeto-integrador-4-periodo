# Relatório de QA: e2e e roteiro de segurança em produção

Segunda camada de testes da QA (issue #27), depois dos testes unitários e de integração.
Os testes rodaram contra o ambiente publicado, com a API de produção, em 16/11/2026. O teste de
isolamento com duas empresas reais (seção 2, "Acesso a dado de outra empresa") rodou em
17/11/2026, depois que a API ganhou a rota de exclusão de empresa (`DELETE /empresa`, #90).

| item | valor |
|---|---|
| Site | `https://stcoldtrackweb7319.z15.web.core.windows.net` |
| API | `https://func-coldtrack-7319.azurewebsites.net/api` |
| Front testado | `Front-End-pi`, `main` no commit `c45e30d` |
| API testada | a que estava publicada na data (`main` deste repositório no commit `3b2be87`); no isolamento com duas empresas, `main` no commit `6b57c28` |
| Navegador | Chromium (Playwright), 1 worker, em série |
| Contas | gestor e operador da empresa de demonstração, só para entrar; senha errada nunca foi enviada a elas |

## 1. Suíte e2e real

Comandos (no `Front-End-pi`, com as variáveis `COLDTRACK_GESTOR_EMAIL/SENHA` e
`COLDTRACK_OPERADOR_EMAIL/SENHA` definidas no ambiente):

```bash
npm ci
npm run test:e2e:real
npm run test:e2e:real:limpar
```

Resultado da execução completa (4,0 min): **57 testes, 56 passaram, 1 falhou, 0 pulados**.
Os 57 incluem os 2 logins de preparação (`login.setup.js`). O teste do assistente do painel
(`REAL-ASSIST-01`) e os dois do chat com IA (`REAL-PUB-05` e `REAL-PUB-09`) passaram, ou seja,
`/assistente` e `/chat` estavam no ar.

| arquivo | casos | resultado |
|---|---|---|
| `login.setup.js` | REAL-AUTH-01, 02 | passou |
| `01-publico.spec.js` | REAL-PUB-01 a 09 | passou |
| `02-autenticacao.spec.js` | REAL-AUTH-03 a 07 | passou |
| `03-api-contrato.spec.js` | REAL-API-01 a 06, REAL-CAD-01 | passou |
| `04-gestor-cadastros.spec.js` | REAL-GES-01 a 06 | passou |
| `05-gestor-usuario.spec.js` | REAL-USR-01 a 04 | passou |
| `06-operador.spec.js` | REAL-OPE-01 a 03 | passou |
| `07-telas.spec.js` | 14 telas (7 em 1280 px, 7 em 390 px) e REAL-TEL-CSV | 13 de 14 telas passaram; **`/viagens` em 390 px falhou**; CSV passou |
| `08-assistente.spec.js` | REAL-ASSIST-01 | passou |

### Falha observada: `REAL-TEL /viagens em 390 px`

Na execução completa, o texto "Azure conectado" (selo online do painel) não apareceu em 20 s
na tela `/viagens` a 390 px. Reexecutado isoladamente, o mesmo teste passou; em mais 3
execuções de `/viagens` e `/dashboard` a 390 px (12 testes) nenhum falhou. O defeito não se
reproduz, então foi tratado como **intermitente** (hipótese: lentidão pontual da API ou da
primeira chamada da Function após ociosidade; não confirmada), sem issue de bug aberta. Se
voltar a ocorrer, abrir bug com o rastro de `test-results-real/`.

### Limpeza

`npm run test:e2e:real:limpar` respondeu `Removidos: 0` e `Nenhum registro QA-* na API`
(os `afterAll` da suíte já tinham apagado tudo). Conferência final pela API, com o token do
gestor: nenhum usuário, sensor, veículo ou viagem com prefixo `QA-`/`qa-` e nenhum e-mail
`@teste.coldtrack.app`. A suíte não cria empresas; as duas empresas do teste de isolamento
foram apagadas pela rota `DELETE /empresa` (seção 2).

## 2. Roteiro de segurança (`seguranca.md`) contra produção

Feito por script contra a API, com um usuário operador descartável
(`qa-<timestamp>@teste.coldtrack.app`) criado e removido no mesmo roteiro. As contas fixas
não receberam senha errada. As 10 senhas erradas somadas ficaram abaixo do limite de 20 por IP.

### Login com senha errada e bloqueio por tentativas

| caso | resultado observado | esperado | veredito |
|---|---|---|---|
| SEG-01 e-mail inexistente | `401`, mensagem `e-mail ou senha incorretos. Se errou várias vezes, aguarde alguns minutos.` (334 ms) | `401` igual ao de senha errada | passou |
| SEG-02 senha errada, 4 vezes seguidas | `401` com a mesma mensagem nas 4 | `401` igual | passou |
| SEG-03 senha certa depois de 4 erradas | `200` | entra; o contador não chegou a 5 | passou |
| SEG-04 5 senhas erradas seguidas (contador zerado pelo SEG-03) | `401` nas 5, mesma mensagem | `401` igual | passou |
| SEG-05 senha **certa** logo após a 5ª falha | `401`, mesma mensagem (conta em espera) | `401` | passou |
| SEG-06 senha errada durante a espera | `401`, mesma mensagem | `401` | passou |
| SEG-07 senha certa 66 s após a 5ª falha | `200` | espera de 1 min vencida, entra | passou |

A resposta de conta em espera é igual à de e-mail inexistente e de senha errada: não revela
quem tem conta nem quem está bloqueado. A espera de 2 min (6ª falha em diante) e o limite de
20 falhas por IP (`429`) **não foram exercitados**, para não bloquear o IP de quem roda os
testes nem a conta por mais tempo; seguem cobertos só pelos testes de integração.

### Token adulterado, expirado ou ausente

Token do usuário operador, alterado campo a campo. Os pedidos foram a `GET /eu`, e o
`GET /usuarios` com payload adulterado.

| caso | resultado observado | esperado | veredito |
|---|---|---|---|
| SEG-08 claims do token | `sub, nome, perfil, emp, ver, iat, exp` | sem dado sensível | passou |
| SEG-09a sem token | `401` `faça login para continuar` | `401` | passou |
| SEG-09b texto qualquer (`abc.def.ghi`) | `401` | `401` | passou |
| SEG-09c payload com `perfil=gestor`, assinatura antiga | `401` | `401` | passou |
| SEG-09d `exp` no passado, assinatura antiga | `401` | `401` | passou |
| SEG-09e `alg: none` | `401` | `401` | passou |
| SEG-09f assinatura removida | `401` | `401` | passou |
| SEG-10 `GET /usuarios` com perfil adulterado para gestor | `401` | `401` | passou |
| SEG-11 token válido do operador em `GET /eu` | `200`, `perfil=operador` | `200` | passou |
| SEG-12 operador em `GET /usuarios` | `403` | `403` | passou |
| SEG-13 `POST /sair` | `204` | `204` | passou |
| SEG-14 mesmo token depois de `POST /sair` | `401` | `401` | passou |

Limite do teste: não há acesso ao `JWT_SECRET`, então não dá para assinar um token legítimo
já vencido. O caso SEG-09d prova que a assinatura é conferida, não que o vencimento (`exp`) é
verificado de forma isolada. O vencimento da sessão aparece na interface em `REAL-AUTH-07`
(passou), que testa o painel com `expiraEm` no passado, não a API.

### Acesso a dado de outra empresa

**Primeira rodada (16/11/2026), sem segunda empresa.** `POST /empresas` não podia ser desfeito
(não havia rota para apagar empresa), então os casos abaixo usaram, com o token do gestor da
empresa de demonstração, ids que não existem na empresa dele, incluindo o formato interno
`E-00000000~<código>`.

| caso | resultado observado | esperado | veredito |
|---|---|---|---|
| ISO-01a `GET /leituras?deviceId=E-00000000~sensor-x` | `404` `dispositivo não encontrado` | `404` | passou |
| ISO-01b `GET /leituras` de sensor inexistente | `404` `dispositivo não encontrado` (igual ao anterior) | `404` | passou |
| ISO-01c `DELETE /veiculos/E-00000000~CT-001` | `404` `não encontrado` | `404` | passou |
| ISO-01d `DELETE /viagens/V-ZZZZZZ` | `404` `não encontrado` | `404` | passou |
| ISO-01e `DELETE /dispositivos/E-00000000~x` | `404` `dispositivo não encontrado` | `404` | passou |
| ISO-01f `DELETE` e `PUT /usuarios/<e-mail de fora>` | `404` `não encontrado` nos dois | `404` | passou |
| ISO-01g `PUT /veiculos/E-00000000~CT-001` | `400` (corpo de teste sem `id` e `deviceId`) | `404` | inconclusivo; refeito como ISO-W3 e ISO-W4 abaixo |
| ISO-02 `POST /veiculos` com `empresaId` no corpo | `400` (faltou `deviceId`) | `empresaId` ignorado | inconclusivo; refeito como ISO-C1 abaixo |

**Segunda rodada (17/11/2026), com duas empresas reais.** Feita por script contra a API de
produção, depois da publicação de `DELETE /empresa` (run "Publicar API" do commit `6b57c28`,
concluído com sucesso; `GET /api/openapi.json` já listava `/empresa`). Foram criadas por
`POST /empresas` duas empresas descartáveis, A (`E-40DA926B`) e B (`E-DB31C69A`), com gestor de
e-mail `qa-iso-<a|b>-<timestamp>@teste.coldtrack.app` e senha aleatória. Cada uma recebeu 2
sensores (`qa-iso-<a|b>-<timestamp>` e `...-2`), 1 veículo (`QA-A012945` / `QA-B012945`), 1
viagem e 1 leitura enviada pelo próprio sensor com a chave dele (`POST /telemetria`, `201`).
Todas as chamadas abaixo usam o token do gestor de A contra itens de B, salvo indicação. Nenhuma
conta fixa foi usada.

| caso | pedido (token de A) | resultado observado | esperado | veredito |
|---|---|---|---|---|
| ISO-L1 | `GET /dispositivos` | `200`, só os 2 sensores de A | nenhum de B | passou |
| ISO-L2 | `GET /veiculos` | `200`, só `QA-A012945` | nenhum de B | passou |
| ISO-L3 | `GET /viagens` | `200`, só a viagem de A | nenhuma de B | passou |
| ISO-L4 | `GET /usuarios` | `200`, só o gestor de A | nenhum de B | passou |
| ISO-L5 | `GET /leituras?deviceId=<sensor de B>` | `404` `dispositivo não encontrado` | `404` | passou |
| ISO-L6 | mesmo pedido com o token de B (controle) | `200`, 1 leitura | `200` | passou |
| ISO-W1 | `PUT /dispositivos/<sensor de B>` (troca de chave) | `404` | `404` | passou |
| ISO-W2 | `DELETE /dispositivos/<sensor de B>` | `404` | `404` | passou |
| ISO-W3 | `PUT /veiculos/QA-B012945` com corpo válido (`id`, `tipo`, `deviceId` de um sensor livre de A, `perfil`) | `404` `não encontrado` | `404` | passou (refaz ISO-01g) |
| ISO-W4 | `PUT /veiculos/E-DB31C69A~QA-B012945` (id interno de B), mesmo corpo | `404` `não encontrado` | `404` | passou |
| ISO-W5 | `DELETE /veiculos/QA-B012945` | `404` | `404` | passou |
| ISO-W6 | `PUT /viagens/<viagem de B>` com corpo válido | `404` | `404` | passou |
| ISO-W7 | `DELETE /viagens/<viagem de B>` | `404` | `404` | passou |
| ISO-W8 | `PUT /usuarios/<gestor de B>` (redefinir senha) | `404` | `404` | passou |
| ISO-W9 | `DELETE /usuarios/<gestor de B>` | `404` | `404` | passou |
| ISO-C1 | `POST /veiculos` válido com `"empresaId": "E-DB31C69A"` no corpo | `201` | criado em A | passou (refaz ISO-02) |
| ISO-C2 | `GET /veiculos` (A) | o veículo novo está em A, com `empresaId` `E-40DA926B` | em A | passou |
| ISO-C3 | `GET /veiculos` (token de B) | só `QA-B012945` | não aparece em B | passou |
| ISO-C4 / C5 | `POST /dispositivos` com `empresaId` de B; `GET /dispositivos` de B | `201`; B continua com os 2 sensores dele | criado em A | passou |
| ISO-C6 / C7 | `POST /usuarios` (operador) com `empresaId` de B; `GET /usuarios` de B | `201` com `empresaId` de A; B continua só com o gestor | criado em A | passou |
| ISO-B1 | `GET /veiculos` (B), depois dos ataques | tipo, sensor e perfil do veículo de B inalterados | intacto | passou |
| ISO-B2 | `GET /viagens` (B) | viagem de B inalterada | intacta | passou |
| ISO-B3 | `POST /telemetria` com a chave original do sensor de B | `201` (a chave não foi trocada por ISO-W1) | `201` | passou |
| ISO-B4 | `POST /login` do gestor de B, senha certa | `200` (a senha não foi trocada por ISO-W8) | `200` | passou |

Resultado: os 2 casos inconclusivos da primeira rodada passaram, e A não leu, alterou nem apagou
nenhum item de B; o `empresaId` enviado no corpo foi ignorado em veículo, sensor e usuário.

#### Exclusão das duas empresas e conferência

| caso | pedido | resultado observado | esperado | veredito |
|---|---|---|---|---|
| DEL-B0 | B pede `DELETE /empresa` com `confirmacao` igual ao nome de A | `400` `confirmacao: não confere com o nome da empresa` | `400`, nada apagado | passou |
| DEL-B1 | gestor de A pede `DELETE /empresa` com o nome de B e a própria senha | `400` (a empresa vem do token, não do corpo) | `400` | passou |
| DEL-B2 | B pede com o próprio nome e a senha | `200` em 608 ms, `removidos`: 2 sensores, 2 leituras, 1 viagem, 1 veículo, 1 usuário, 1 empresa | tudo de B | passou |
| DEL-A0 | A pede com o nome de B | `400` | `400` | passou |
| DEL-A2 | A pede com o próprio nome e a senha | `200` em 625 ms, `removidos`: 3 sensores, 1 leitura, 1 viagem, 2 veículos, 2 usuários, 1 empresa | tudo de A, inclusive o criado em ISO-C1, C4 e C6 | passou |
| POS-A1 / B1 | `POST /login` dos dois gestores com a senha certa | `401` | `401` | passou |
| POS-A2 / B2 | token antigo em `GET /eu` | `401` | `401` | passou |
| POS-A3 / B3 | token antigo em `GET /veiculos` | `401` | `401` | passou |
| POS-A4 / B4 | repetir `DELETE /empresa` com o token antigo | `401` | `401` | passou |
| POS-A5 / B5 | `POST /telemetria` dos 4 sensores com a chave certa de cada um | `401` nos 4 (sensor não registrado) | `401` | passou |

As contagens batem item a item com o que o script criou (A: os 2 sensores, o de ISO-C4, o
veículo e o de ISO-C1, o gestor e o operador de ISO-C6; B: 2 leituras, a de preparação e a de
ISO-B3), então nada das duas empresas ficou no banco. Total: 43 chamadas verificadas, 0 falhas.

### `/predict`

| caso | resultado observado | esperado | veredito |
|---|---|---|---|
| PRED-01 operador, `mes=10&hora=15` | `200`, probabilidade 0,9839, nível `alto`, 62 horas de histórico, modelo `clima-a307-30c-v1` | igual ao exemplo de `api.md` | passou |
| PRED-02 gestor, `mes=1&hora=3` | `200`, probabilidade 0, nível `baixo` | `200` | passou |
| PRED-03 sem parâmetros | `400` `mes: inteiro de 1 a 12`, `hora: inteiro de 0 a 23` | `400` | passou |
| PRED-03 `mes=13`, `mes=0`, `mes=abc` | `400` `mes: inteiro de 1 a 12` | `400` | passou |
| PRED-03 `hora=24`, `hora=-1` | `400` `hora: inteiro de 0 a 23` | `400` | passou |
| PRED-03 só `mes=5` | `400` `hora: inteiro de 0 a 23` | `400` | passou |
| PRED-04 sem token | `401` | `401` | passou |
| PRED-05 token adulterado | `401` | `401` | passou |

### Selo online

`REAL-TEL` abre as 7 telas do painel em 1280 px e 390 px e exige o selo "Azure conectado".
Passou em 13 das 14 combinações; a falha de `/viagens` em 390 px foi intermitente (seção 1).

## 3. Resumo

- Suíte e2e real: 56 de 57 passaram, 0 pulados, 1 falha intermitente que não se reproduziu.
- Roteiro de segurança: todos os casos executados passaram. Os 2 inconclusivos da primeira
  rodada (ISO-01g, ISO-02) foram refeitos com duas empresas reais e passaram (ISO-W3, ISO-W4,
  ISO-C1).
- Isolamento com duas empresas reais: 43 chamadas, 0 falhas; as duas empresas foram apagadas
  por `DELETE /empresa` e a conferência pela API não achou nada delas.
- Bugs reais abertos: nenhum.
- Fora do que foi feito, por falta de meio seguro em produção: vencimento de token legítimo,
  espera de 2 min ou mais e limite de 20 falhas por IP.
- Dados de teste: todos removidos e conferidos, inclusive as duas empresas do teste de
  isolamento.

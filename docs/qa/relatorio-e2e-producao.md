# Relatório de QA: e2e e roteiro de segurança em produção

Segunda camada de testes da QA (issue #27), depois dos testes unitários e de integração.
Os testes rodaram contra o ambiente publicado, com a API de produção, em 16/11/2026.

| item | valor |
|---|---|
| Site | `https://stcoldtrackweb7319.z15.web.core.windows.net` |
| API | `https://func-coldtrack-7319.azurewebsites.net/api` |
| Front testado | `Front-End-pi`, `main` no commit `c45e30d` |
| API testada | a que estava publicada na data (`main` deste repositório no commit `3b2be87`) |
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
`@teste.coldtrack.app`. A suíte não cria empresas (a API não tem rota para apagá-las), então
não sobrou empresa de teste.

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

Não foi criada uma segunda empresa: `POST /empresas` não pode ser desfeito (não há rota para
apagar empresa) e deixaria resíduo em produção. Os casos abaixo usam, com o token do gestor,
ids que não existem na empresa dele, incluindo o formato interno `E-00000000~<código>` de
outra empresa. É o mesmo caminho de código de um item alheio (que `seguranca.md` descreve
como indistinguível de item inexistente), mas **não substitui um teste com duas empresas reais**.

| caso | resultado observado | esperado | veredito |
|---|---|---|---|
| ISO-01a `GET /leituras?deviceId=E-00000000~sensor-x` | `404` `dispositivo não encontrado` | `404` | passou |
| ISO-01b `GET /leituras` de sensor inexistente | `404` `dispositivo não encontrado` (igual ao anterior) | `404` | passou |
| ISO-01c `DELETE /veiculos/E-00000000~CT-001` | `404` `não encontrado` | `404` | passou |
| ISO-01d `DELETE /viagens/V-ZZZZZZ` | `404` `não encontrado` | `404` | passou |
| ISO-01e `DELETE /dispositivos/E-00000000~x` | `404` `dispositivo não encontrado` | `404` | passou |
| ISO-01f `DELETE` e `PUT /usuarios/<e-mail de fora>` | `404` `não encontrado` nos dois | `404` | passou |
| ISO-01g `PUT /veiculos/E-00000000~CT-001` | `400` (corpo de teste sem `id` e `deviceId`) | `404` | **inconclusivo**: a validação respondeu antes |
| ISO-02 `POST /veiculos` com `empresaId` no corpo | `400` (faltou `deviceId`) | `empresaId` ignorado | **inconclusivo**: a validação respondeu antes |

Os dois inconclusivos exigiriam um sensor e um veículo de teste completos; ficam cobertos
pelos testes de integração do PR #20.

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
- Roteiro de segurança: todos os casos executados passaram; 2 inconclusivos (ISO-01g, ISO-02).
- Bugs reais abertos: nenhum.
- Fora do que foi feito, por falta de meio seguro em produção: isolamento com duas empresas
  reais, vencimento de token legítimo, espera de 2 min ou mais e limite de 20 falhas por IP.
- Dados de teste: todos removidos e conferidos; nenhuma empresa de teste foi criada.

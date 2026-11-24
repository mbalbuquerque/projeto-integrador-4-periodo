# Segurança do ColdTrack: Projeto Final

## 1. Identificação

- **Projeto:** ColdTrack (monitoramento de temperatura de carga refrigerada).
- **Código de missão:** `XXXXXX` (marcador de 6 caracteres aguardando envio oficial do professor na thread do Teams/AVA). Em tempo de execução, o valor é lido dinamicamente da App Setting `MISSAO_CODIGO` do Azure Functions — nunca hard-coded no repositório.
- **Integrantes:**

| Nome | Usuário no GitHub |
|---|---|
| Everson | Everson9 |
| Emmanuel | MrLlouis |
| Enzo | Benzo171 |
| Marcelo | mbalbuquerque |
| Gabriel | gabrielfranca42 |

## 2. O projeto

Placa **ESP32-C3** com sensor **DHT11** monitorando temperatura e umidade dentro do baú refrigerado. A placa envia leituras a cada 20 segundos via HTTPS (JSON) para a API no Azure Functions (`POST /api/telemetria`), autenticada com cabeçalho `x-device-key` (chave aleatória por sensor, hash SHA-256 no Cosmos DB). As leituras são gravadas no **Cosmos DB** (container `leituras`, particionado por `deviceId`) e expostas pelo painel web em **React + Vite** (PWA instalável, `manifest.json` + `sw.js`), publicado no Azure Storage Static Web Apps. Cada empresa (tenant) só enxerga os próprios sensores, veículos, viagens e usuários — isolamento feito via `empresaId` no token JWT e em todas as consultas.

Arquitetura real:
- **Back-end:** Python 3.11, Azure Functions (HTTP triggers), Cosmos DB (NoSQL), JWT HS256 (8h), scrypt para senhas.
- **Front-end:** React 18 + Vite, React Router, PWA, Web Push (VAPID), consumindo a API via `fetch` com `Authorization: Bearer <token>`.
- **Comunicação:** REST API HTTPS (`https://func-coldtrack-7319.azurewebsites.net/api`).

Documentos de base: [`modelo-ameacas.md`](modelo-ameacas.md), [`uso-de-ia.md`](uso-de-ia.md), [`docs/stride.md`](../docs/stride.md) e [`docs/seguranca.md`](../docs/seguranca.md).

## 3. Controle 1: 2FA com TOTP (login)

- **Ameaça:** senha vazada de um gestor dá acesso a tudo da empresa (Spoofing).
- **Controle:** segundo passo no login com código de 6 dígitos (TOTP RFC 6238) ou código de recuperação de uso único; código não pode ser reaproveitado (anti-replay via contador TOTP). Issue #113.
- **Implementação (back-end):**
  - `cloud/function/seguranca.py`: funções `gerar_totp_secret()`, `totp_uri()`, `verificar_totp()` (anti-replay), `gerar_recovery_codes()`, `hash_recovery_codes()`, `verificar_recovery_code()`, `gerar_desafio_2fa()`, `ler_desafio_2fa()`, `log_2fa_bloqueado()`.
  - `cloud/function/function_app.py`: rotas `POST /2fa/iniciar` (gera segredo + QR `otpauth://`), `POST /2fa/ativar` (valida 1º TOTP, grava segredo + 10 recovery codes hash scrypt), `POST /2fa/desativar` (senha + TOTP/recovery), `POST /login/2fa` (valida desafio JWT 5min + TOTP/recovery, emite token 8h). Login `POST /api/login` retorna `{exige2fa: true, desafio}` se `totpAtivo=true`.
  - `cloud/function/requirements.txt`: `pyotp>=2.9.0`.
- **Implementação (front-end):**
  - `src/lib/doisFatores.js`: utilitários `limparCodigo()`, `limparRecuperacao()`, `segredoDaUri()`, `agruparSegredo()`, `textoCodigos()`.
  - `src/pages/Configuracoes/DoisFatores.jsx`: componente completo (etapas: `inicio` → `qr` → `codigos` → `ativo` / `desativar`), desenha QR no navegador (`qrcode-generator`), mostra segredo base32 agrupado, 10 códigos de recuperação com copiar/baixar `.txt`.
  - `src/pages/Login/Login.jsx`: `SegundoPasso` com input 6 dígitos (`autocomplete="one-time-code"`), toggle para recovery code (8 chars), botão Voltar.
- **Como testar:** scripts em [`seguranca/testes/test_2fa.py`](testes/test_2fa.py) e `python -m unittest cloud.function.test_seguranca` (testes unitários TOTP, recovery, anti-replay, login/2fa).
- **Resultado antes/depois:** arquivos em [`evidencias/`](evidencias/) (preenchido na #115).
- **Limitações:** o motorista não tem 2FA; quem perde o aplicativo e os códigos de recuperação precisa de um administrador.

## 4. Controle 2: proteção contra IDOR (verificação de dono)

- **Ameaça:** usuário da empresa A troca o ID e lê ou altera dados da empresa B.
- **Controle:** `exigir_dono(recurso_tipo, recurso_id, usuario)` em toda rota que recebe ID; o dono vem sempre do token (JWT `sub` + `emp`), nunca do body/query/header. Mesma resposta (404) para "não existe" e "é de outro". Issue #114.
- **Implementação (back-end):**
  - `cloud/function/function_app.py`: função `exigir_dono()` (linhas ~256-320) validando `dispositivo`, `veiculo`, `viagem`, `leitura`/`sensor`, `usuario` contra `empresaId` do token. Registra `log_idor_bloqueado()` com `MISSAO_CODIGO`.
  - Rotas protegidas: `GET /api/leituras?deviceId=` (linha ~1293), `GET /api/predict/sensor?deviceId=` (linha ~1380), `GET/POST/PUT/DELETE /api/dispositivos/{id}` (linha ~1360), `GET/POST/PUT/DELETE /api/veiculos/{id}` (linha ~1450), `GET/POST/PUT/DELETE /api/viagens/{id}` (linha ~1500), `GET/POST/PUT/DELETE /api/usuarios/{id}` (linha ~1550).
- **Como testar:** `python -m unittest cloud.function.test_acesso.TestAcessoIDOR` e script [`seguranca/testes/test_idor.py`](testes/test_idor.py) (usuário A tenta ler/alterar dispositivo do usuário B → 404; usuário B acessa próprio → 200).
- **Resultado antes/depois:** o mesmo teste no commit `d44b301` (ataque funciona) e no atual (404), em [`evidencias/`](evidencias/).
- **Limitações:** a checagem depende de o código do dono estar no token; rota nova precisa chamar `exigir_dono`.

## 5. Log de bloqueios

Os dois controles registram o bloqueio com o código de missão (app setting `MISSAO_CODIGO`, nunca no código): `2fa bloqueado [...]` e `idor bloqueado [...]`. Consulta no Log Analytics em [`evidencias/LEIAME.md`](evidencias/LEIAME.md).

## 6. Segredos no histórico

Verificação feita em 23/11/2026 nos 292 commits de todas as branches: nenhum segredo real encontrado (chaves de conta, tokens, chave privada, senhas literais). Arquivos `secrets.h`, `local.settings.json` e `.env` nunca entraram no Git; só os `*.example`.

## 7. Evidências

Prints, logs e vídeos de até 90 s, todos com o código de missão no nome, em [`evidencias/`](evidencias/). Roteiro de captura em [`evidencias/LEIAME.md`](evidencias/LEIAME.md).
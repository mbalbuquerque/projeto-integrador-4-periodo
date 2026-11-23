# Segurança do ColdTrack: Projeto Final

## 1. Identificação

- **Projeto:** ColdTrack (monitoramento de temperatura de carga refrigerada).
- **Código de missão:** CÓDIGO-DE-MISSÃO a preencher (6 caracteres enviados pelo professor).
- **Integrantes:**

| Nome | Usuário no GitHub |
|---|---|
| Everson | Everson9 |
| Emmanuel | MrLlouis |
| Enzo | Benzo171 |
| Marcelo | mbalbuquerque |
| Gabriel | gabrielfranca42 |

## 2. O projeto

Placa ESP32-C3 com sensor DHT dentro do baú, que envia leituras por HTTPS a uma API em Azure
Functions. As leituras ficam no Cosmos DB e aparecem num painel web em React (também PWA).
Cada empresa só enxerga os próprios sensores. _Parte da placa: Enzo completa._

Documentos de base: [`modelo-ameacas.md`](modelo-ameacas.md), [`uso-de-ia.md`](uso-de-ia.md),
[`docs/stride.md`](../docs/stride.md) e [`docs/seguranca.md`](../docs/seguranca.md).

## 3. Controle 1: 2FA com TOTP (login)

- **Ameaça:** senha vazada de um gestor dá acesso a tudo da empresa (Spoofing).
- **Controle:** segundo passo no login com código de 6 dígitos (TOTP) ou código de recuperação de uso único; código não pode ser reaproveitado. Issue #113.
- **Como testar:** comandos em [`testes/`](testes/) _(preenchido pelo PR da #113)_.
- **Resultado antes/depois:** arquivos em [`evidencias/`](evidencias/) _(preenchido na #115)_.
- **Limitações:** o motorista não tem 2FA; quem perde o aplicativo e os códigos de recuperação precisa de um administrador.

## 4. Controle 2: proteção contra IDOR (verificação de dono)

- **Ameaça:** usuário da empresa A troca o ID e lê ou altera dados da empresa B.
- **Controle:** `exigir_dono` em toda rota que recebe ID; o dono vem sempre do token, nunca do corpo. Mesma resposta (404) para "não existe" e "é de outro". Issue #114.
- **Como testar:** `python -m unittest test_idor` em `cloud/function` e o script de [`testes/`](testes/) _(preenchido pelo PR da #114)_.
- **Resultado antes/depois:** o mesmo teste no commit `d44b301` (ataque funciona) e no atual (404), em [`evidencias/`](evidencias/).
- **Limitações:** a checagem depende de o código do dono estar no token; rota nova precisa chamar `exigir_dono`.

## 5. Log de bloqueios

Os dois controles registram o bloqueio com o código de missão (app setting `MISSAO_CODIGO`, nunca no código): `2fa bloqueado [...]` e `idor bloqueado [...]`. Consulta no Log Analytics em [`evidencias/LEIAME.md`](evidencias/LEIAME.md).

## 6. Segredos no histórico

Verificação feita em 23/11/2026 nos 292 commits de todas as branches: nenhum segredo real encontrado (chaves de conta, tokens, chave privada, senhas literais). Arquivos `secrets.h`, `local.settings.json` e `.env` nunca entraram no Git; só os `*.example`.

## 7. Evidências

Prints, logs e vídeos de até 90 s, todos com o código de missão no nome, em [`evidencias/`](evidencias/). Roteiro de captura em [`evidencias/LEIAME.md`](evidencias/LEIAME.md).
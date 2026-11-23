# Ficha OWASP do ColdTrack (IoT Top 10 e API Security Top 10)

Situação em 23/11/2026. Cada linha traz o risco, o controle que existe no repositório e onde
conferir. Status: **Atendido** (há controle e evidência), **Parcial** (existe, mas falta parte) ou
**Aberto** (sem controle; fica registrado como limitação). Referências: OWASP Internet of Things
Top 10 (2018) e OWASP API Security Top 10 (2023). O modelo de ameaças está em
[`stride.md`](stride.md); os controles da API em [`seguranca.md`](seguranca.md); as varreduras
em [`relatorio-seguranca.md`](relatorio-seguranca.md).

## API Security Top 10 (2023)

| ID | Risco | Controle no ColdTrack | Evidência | Status |
|---|---|---|---|---|
| API1 | Autorização quebrada em nível de objeto | O token leva a empresa e toda consulta filtra por ela; item de outra empresa responde `404`, igual a item inexistente. Veículos e viagens têm id `<empresa>~<código>`. A chave de um sensor só vale para o próprio `deviceId` | `function_app.py` (`_dispositivo_da_empresa`); testes `test_predict_sensor.py` (sensor de outra empresa, 404), `test_heartbeat.py`, `test_online.py`, `test_excluir_empresa.py`, `test_assistente.py` | Parcial: a matriz completa (todas as rotas com id, duas empresas) está na issue #114 |
| API2 | Autenticação quebrada | Senha com scrypt e sal por usuário; JWT HS256 de 8 h, `alg: none` recusado; sessão revogável (`POST /sair`, troca de senha e remoção derrubam o token); mesma resposta `401` para e-mail inexistente e senha errada; espera crescente de 1 a 15 min e 20 falhas por IP a cada 15 min | `seguranca.py`, `limites.py`; `test_seguranca.py`, `test_limites.py`; tabela em [`seguranca.md`](seguranca.md) | Atendido (2FA com TOTP: issue #113) |
| API3 | Autorização quebrada em nível de propriedade | A API monta o documento só com os campos previstos e põe a empresa do token; empresa, perfil de quem cria a empresa, hash e versão da sessão enviados pelo cliente são ignorados. Gestor não redefine a própria senha em `PUT /usuarios` (só em `POST /senha`, com a atual) | `cadastros.py`, `contrato.py`; `test_acesso.py` | Atendido |
| API4 | Consumo irrestrito de recursos | Limite por rota (login, cadastro de empresa, troca de senha, exclusão de empresa, chat, assistente, motorista, heartbeat, previsão); cotas diárias no chat e no assistente, contadas no Cosmos e somadas entre instâncias; leitura validada por faixa (`contrato.py`) | [`seguranca.md`](seguranca.md) (tabela rota × limite); `test_limites.py` | Parcial: não há teto explícito para o tamanho do corpo da requisição além do limite da plataforma Azure Functions |
| API5 | Autorização quebrada em nível de função | Perfil relido no banco a cada chamada (vale o atual, não o do token); cadastro sem perfil ou sem empresa é negado com `403`; rotas de cadastro só para gestor | `seguranca.py`; `test_seguranca.py` (perfil desconhecido), `test_acesso.py` | Atendido |
| API6 | Acesso irrestrito a fluxos de negócio sensíveis | `POST /empresas` com 5 cadastros por hora por IP; `DELETE /empresa` com quatro travas (só gestor, só a empresa do token, nome ou código digitado, senha atual) e 5 pedidos por hora | [`seguranca.md`](seguranca.md); `test_excluir_empresa.py`, `test_limites.py` | Atendido (sem CAPTCHA contra quem usa vários IPs, registrado na ficha de limites) |
| API7 | Falsificação de requisição do lado do servidor (SSRF) | A API não busca URL escolhida pelo usuário. A única saída para endereço vindo do cliente é o Web Push, que só faz `POST` para os hosts de push dos navegadores (lista fixa) e limita o endereço a 2048 caracteres | `push.py` (`HOSTS_PUSH`, `ENDPOINT_MAX`); `test_push.py` | Atendido |
| API8 | Configuração incorreta de segurança | HTTPS obrigatório (`httpsOnly`), TLS mínimo 1.2, FTPS apenas, CORS só para o painel publicado; cabeçalhos `Strict-Transport-Security`, `X-Content-Type-Options`, `Cache-Control: no-store`, `Referrer-Policy`; `/api/docs` com CSP por hash; chaves do Azure OpenAI desligadas (acesso por identidade gerenciada) | `infra/main.bicep`; `function_app.py` (cabeçalhos); `test_cabecalhos.py`; ZAP com 0 alertas altos | Atendido |
| API9 | Gestão inadequada do inventário | Spec OpenAPI em inglês, publicada em `/api/openapi.json` e `/api/docs`; o teste falha se uma rota existir sem estar na spec (ou o contrário) e se alguma operação ficar sem descrição ou sem esquema de segurança. Um único ambiente de produção, sem versões antigas expostas | `cloud/function/openapi.json`; `test_openapi.py` | Atendido |
| API10 | Consumo inseguro de APIs | A resposta do Azure OpenAI (chat e assistente) não é confiável: o bloco de dados vai marcado como não confiável, o prompt proíbe seguir instruções dele e links que não são do site viram `[link removido]`. Leituras do sensor passam pela validação de faixa e de tempo antes de gravar | `chat.py`, `assistente.py`, `contrato.py`; `test_chat.py`, `test_assistente.py`, `test_contrato.py` | Atendido |

## Internet of Things Top 10 (2018)

| ID | Risco | Controle no ColdTrack | Evidência | Status |
|---|---|---|---|---|
| I1 | Senhas fracas, previsíveis ou fixas no código | Cada sensor tem chave aleatória de 32 bytes, mostrada uma vez; o banco guarda só o SHA-256. Wi-Fi, ID e chave chegam à placa pelo cabo USB (painel > Sensores), e `secrets.h` real não vai ao repositório (só `secrets.example.h`). Gerar uma nova chave invalida a anterior na hora | `function_app.py` (`chaveHash`, nova chave); `firmware/coldtrack/secrets.example.h`; histórico do Git sem segredo real (conferido, abaixo) | Atendido |
| I2 | Serviços de rede inseguros | A placa não abre porta nem serviço: só faz conexões de saída (HTTPS para a API e MQTT/TLS na 8883 para o ThingSpeak). Não há servidor web, Telnet nem OTA no firmware | `firmware/coldtrack/coldtrack.ino` (sem `WebServer` nem `ArduinoOTA`) | Atendido |
| I3 | Interfaces inseguras do ecossistema | A API e o painel seguem a tabela da API acima; o painel não usa `innerHTML` (regra do ESLint que derruba o CI) e escapa o CSV exportado | `eslint.config.js` do painel; `seguranca.md` | Atendido |
| I4 | Falta de mecanismo seguro de atualização | A placa só se atualiza por cabo USB, sem OTA; o firmware leva versão (`FW_VERSAO`) e a atualização exige acesso físico | `coldtrack.ino` (`FW_VERSAO`) | Parcial: não há atualização remota assinada |
| I5 | Componentes inseguros ou desatualizados | `pip-audit` e `npm audit` sem alerta alto no workflow Segurança; dependências das duas pilhas e das Actions acompanhadas por Dependabot; imagem da Function é a oficial do Azure Functions | `.github/workflows/seguranca.yml`, `.github/dependabot.yml`; `infra/Dockerfile` | Atendido (o `npm audit` aponta 2 avisos moderados em `react-router`, triados no [relatório de segurança](relatorio-seguranca.md)) |
| I6 | Proteção insuficiente da privacidade | Inventário de dados, retenção, direitos do titular e política de privacidade; exclusão da empresa pelo gestor; e-mails mascarados nos logs; logs sem senha, token nem texto das perguntas | [`lgpd.md`](lgpd.md), [`politica-de-privacidade.md`](politica-de-privacidade.md) | Atendido (exportação dos dados ainda manual) |
| I7 | Transferência e armazenamento inseguros | Envio da placa à API em HTTPS e ao ThingSpeak em MQTT/TLS (porta 8883), com a raiz do certificado fixada no firmware (`setCACert`, `azure_ca.h`); sem `setInsecure`. Cosmos com TLS 1.2 mínimo | `coldtrack.ino` (`setCACert`, `MQTT_PORTA`); `azure_ca.h`; `infra/main.bicep` | Parcial: a chave do sensor fica na flash da placa sem criptografia (ver I10) |
| I8 | Falta de gerenciamento do dispositivo | `POST /heartbeat` a cada 20 s mesmo com o sensor em falha; `online` e `ultimoContato` por sensor na API e no painel; falha de sensor sinalizada (`sensorFalhaDesde`); chave trocável pela API (a anterior deixa de valer); `GET /health` | `function_app.py`; `test_heartbeat.py`, `test_online.py`, `test_health.py` | Atendido |
| I9 | Configurações padrão inseguras | Não existe senha ou chave padrão no código: ID e chave de cada sensor são gerados na API e gravados na placa pela configuração por USB. Os parâmetros (tempos, fila, limites) são constantes do firmware; os segredos ficam em `secrets.h` (fora do Git) e nas app settings da Azure | `coldtrack.ino`; `secrets.example.h`; `.env.example` | Atendido |
| I10 | Falta de endurecimento físico | Sem criptografia da flash nem inicialização segura: quem tem a placa na mão consegue ler a chave do sensor e a senha do Wi-Fi gravadas nela. O risco está no STRIDE (spoofing) e o dano fica limitado a um sensor, cuja chave se troca no painel | [`stride.md`](stride.md) | Aberto (limitação aceita para o protótipo) |

## Limitações aceitas e pendências

- 2FA com TOTP (issue #113) e a matriz completa de autorização por objeto (issue #114) são o
  trabalho do Projeto de Segurança; esta ficha só será atualizada para "Atendido" quando os testes
  entrarem na `main`.
- Sem teto de tamanho do corpo da requisição na API (API4) e sem atualização remota assinada do
  firmware (I4).
- Chave do sensor e Wi-Fi na flash sem criptografia (I7, I10): ativar criptografia de flash e
  inicialização segura do ESP32-C3 exigiria regravar a placa e perderia a gravação por cabo;
  fora do escopo desta entrega.
- A varredura do ZAP é passiva (produção) e ativa só em contêiner de teste; não substitui teste de
  invasão.

## Como conferir

```bash
cd cloud/function
pip install -r requirements.txt -r requirements-dev.txt
pytest --cov=. --cov-branch --cov-fail-under=98     # testes citados acima
bandit -q -r . -x ./test_*.py,./scripts --severity-level medium --confidence-level medium
```

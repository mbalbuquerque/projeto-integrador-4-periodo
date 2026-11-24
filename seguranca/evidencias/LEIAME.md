# Roteiro de evidências (issue #115)

Todo arquivo desta pasta leva o código de missão no nome, por exemplo
`K7Q2M9-otp-sem-codigo-recusado.png`. Sem o código a evidência não vale.
Faça isto **depois** que os PRs do 2FA (#113) e do IDOR (#114) estiverem na `main` e publicados.

## Evidências do depois já gravadas

Geradas em 24/11/2026 (00h38 às 00h40, horário de Brasília) contra a **produção** (painel
`stcoldtrackweb7319` e API `func-coldtrack-7319`), pela interface real do painel, com duas empresas
sintéticas descartáveis (`Teste Seguranca A` e `Teste Seguranca B`, e-mails `@example.com`). A
empresa B tinha um sensor e 10 leituras com `"origem": "simulador"`. As duas empresas foram
**apagadas** no fim (`DELETE /api/empresa`) e o login delas passou a responder 401. Nenhum dado da
empresa real aparece. A faixa preta no rodapé de cada print e vídeo é legenda do teste (não faz
parte do painel). Os arquivos estão com o prefixo `SEM-CODIGO-` até o código de missão chegar;
então basta renomear trocando o prefixo pelo código.

**2FA (TOTP)**

- [`SEM-CODIGO-2fa-ativar-qrcode.png`](SEM-CODIGO-2fa-ativar-qrcode.png): Configurações > ativar 2FA mostra o QR Code (a chave em texto foi coberta no print).
- [`SEM-CODIGO-2fa-codigos-recuperacao.png`](SEM-CODIGO-2fa-codigos-recuperacao.png): ativado com o primeiro código; os 10 códigos de recuperação aparecem uma vez só.
- [`SEM-CODIGO-2fa-login-pede-codigo.png`](SEM-CODIGO-2fa-login-pede-codigo.png): senha certa não dá acesso; a tela pede o código e nenhum token fica no navegador.
- [`SEM-CODIGO-2fa-codigo-errado-recusado.png`](SEM-CODIGO-2fa-codigo-errado-recusado.png): código errado recusado (401).
- [`SEM-CODIGO-2fa-codigo-certo-aceito.png`](SEM-CODIGO-2fa-codigo-certo-aceito.png): código certo aceito (200) e o painel abre.
- [`SEM-CODIGO-2fa-codigo-reusado-recusado.png`](SEM-CODIGO-2fa-codigo-reusado-recusado.png): o mesmo código, 5 s depois e ainda na validade, recusado (401).
- [`SEM-CODIGO-2fa-recuperacao-uma-vez.png`](SEM-CODIGO-2fa-recuperacao-uma-vez.png): código de recuperação aceito (200).
- [`SEM-CODIGO-2fa-recuperacao-reusada-recusada.png`](SEM-CODIGO-2fa-recuperacao-reusada-recusada.png): o mesmo código de recuperação na segunda vez, recusado (401).
- [`SEM-CODIGO-video-2fa.mp4`](SEM-CODIGO-video-2fa.mp4) (25 s): senha, pedido do código, código errado recusado, código certo e painel aberto.

**IDOR**

- [`SEM-CODIGO-idor-b-ve-proprio-sensor.png`](SEM-CODIGO-idor-b-ve-proprio-sensor.png): o usuário B vê o próprio sensor e as leituras dele no painel.
- [`SEM-CODIGO-idor-a-tenta-sensor-de-b.png`](SEM-CODIGO-idor-a-tenta-sensor-de-b.png): no navegador logado como A, `GET /api/leituras?deviceId=<sensor de B>` responde 404.
- [`SEM-CODIGO-idor-a-tenta-apagar-dispositivo-de-b.png`](SEM-CODIGO-idor-a-tenta-apagar-dispositivo-de-b.png): em cima, A tenta `DELETE /api/dispositivos/<sensor de B>` e recebe 404; embaixo, B continua vendo o sensor em Sensores.
- [`SEM-CODIGO-video-idor.mp4`](SEM-CODIGO-video-idor.mp4) (37 s): B vê o sensor; A tenta ler e apagar com o ID de B (404 nos dois); o sensor de B continua lá.

**Log**

- [`SEM-CODIGO-log-bloqueios.txt`](SEM-CODIGO-log-bloqueios.txt): as linhas `2fa bloqueado [...]` e `idor bloqueado [...]` dessa gravação, tiradas do Application Insights da Function App (4 recusas de 2FA e 4 de IDOR, com o e-mail já mascarado pelo log). Saem com `[SEM-CODIGO]` porque a app setting `MISSAO_CODIGO` ainda não foi cadastrada; depois de cadastrada, um teste novo mostra o código de missão no lugar.

## 0. Antes

1. Confirmar com o grupo o código de 6 caracteres do professor e preencher em `seguranca/README.md`.
2. Cadastrar a app setting `MISSAO_CODIGO` na Function App `func-coldtrack-7319` (quem tem acesso ao Azure):
   `az functionapp config appsettings set -g rg-coldtrack -n func-coldtrack-7319 --settings MISSAO_CODIGO=<CODIGO>`.
   O código nunca vai no repositório.

## 1. Prints do OTP (depois)

Salvar como `<CODIGO>-otp-<situacao>.png`:

- login sem código recusado;
- código errado recusado;
- código certo aceito;
- mesmo código de novo recusado;
- código de recuperação aceito uma vez e recusado na segunda.

## 2. Prints do IDOR (depois)

- usuário A tentando ler o sensor de B: 404;
- A tentando alterar o dispositivo de B: 404;
- B usando o próprio sensor normalmente.

## 3. Log do bloqueio no Azure

Portal do Azure > Function App `func-coldtrack-7319` > Monitoramento > Logs. Consulta:

```
traces
| where message has "bloqueado ["
| order by timestamp desc
```

Print com a linha mostrando o código de missão (`<CODIGO>-log-bloqueio.png`).

## 4. Vídeos de até 90 s

Gravador do Windows (`Win + Alt + R`) ou OBS: `<CODIGO>-video-otp.mp4` e `<CODIGO>-video-idor.mp4`,
mostrando o teste do depois rodando. Acima de 25 MB: `ffmpeg -i in.mp4 -vcodec libx264 -crf 28 out.mp4`.

## 5. Segredos

Verificação automática feita em 23/11/2026 (nenhum segredo real no histórico). Refazer depois dos
últimos merges: `git log --all -p | grep -iE "senha|secret|key|token"` não pode mostrar valor real.
O `.env.example` só tem nomes.

## 6. Tag nos dois repositórios

Depois de tudo mergeado e antes de 23h59 de 23/11 (commit depois da tag não conta):

```bash
git checkout main && git pull
git tag entrega-final
git push origin entrega-final
```

Back-end: Emmanuel. Painel (`Front-End-pi`): Enzo.

## 7. Ensaio da alteração ao vivo

O professor escolhe quem faz: mudar a janela de validade do OTP; invalidar os códigos de recuperação
de um usuário; criar um terceiro usuário e mostrar que ele não vê os sensores dos outros; proteger
uma rota nova com `exigir_dono`.
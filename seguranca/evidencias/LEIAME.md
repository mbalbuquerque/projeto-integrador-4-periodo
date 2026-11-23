# Roteiro de evidências (issue #115)

Todo arquivo desta pasta leva o código de missão no nome, por exemplo
`K7Q2M9-otp-sem-codigo-recusado.png`. Sem o código a evidência não vale.
Faça isto **depois** que os PRs do 2FA (#113) e do IDOR (#114) estiverem na `main` e publicados.

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
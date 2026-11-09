# Como contribuir

## Branches

- `everson`: branch de trabalho do back-end, firmware e infraestrutura. Todo push nela que
  altere `cloud/function/` **publica a API em produção** (workflow `publicar-api.yml`).
- `main`: versão consolidada. Recebe a `everson` por pull request quando uma etapa fica pronta, com os
  testes verdes. Depois do merge, a `everson` continua existindo e segue como branch de trabalho.
- **Nunca apagar a `everson`** (nem marcar "apagar branch após o merge" no pull request): a publicação
  da API e do painel e o login do GitHub Actions no Azure dependem dela.
- Mudança maior ou arriscada: criar uma branch a partir de `everson`
  (`everson/<assunto>`), abrir pull request para `everson` e esperar os testes passarem.

Antes de editar, atualizar a branch (`git pull`). Depois de cada pull request para a `main`, trazer
a `main` de volta para a `everson` com merge.

O painel web está em outro repositório, [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi),
com fluxo igual (ver o `CONTRIBUTING.md` de lá).

O login do GitHub Actions no Azure é aceito só para a branch `everson` deste repositório
(ver [`infra/README.md`](infra/README.md)); push em outra branch roda os testes, mas não publica.

## Commits

Mensagens em português, no formato de Conventional Commits:

```
<tipo>: <resumo no imperativo ou descritivo, em minúsculas>

Corpo opcional explicando o porquê.
```

| tipo | uso |
|---|---|
| `feat` | funcionalidade nova |
| `fix` | correção de bug |
| `docs` | só documentação |
| `refactor` | mudança de estrutura sem mudar comportamento |
| `test` | testes |
| `ci` | workflows e publicação |
| `chore` | dependências, configuração, manutenção |

Commits pequenos e com um assunto só. Nunca commitar segredos: `secrets.h`,
`local.settings.json`, connection strings, chaves de sensor ou `JWT_SECRET`.

## Antes de enviar

```bash
cd cloud/function
python -m unittest -v              # todos devem passar
pip install ruff==0.17.4
ruff check .                       # sem apontamentos
```

Mexeu no firmware: compilar as duas variantes, como faz o CI (`.github/workflows/testes.yml`):

```bash
mkdir -p build/coldtrack
cp firmware/coldtrack/coldtrack.ino firmware/coldtrack/azure_ca.h build/coldtrack/
cp firmware/coldtrack/secrets.example.h build/coldtrack/secrets.h
arduino-cli compile --fqbn esp32:esp32:esp32c3 build/coldtrack            # DHT22
echo '#define DHT_TYPE DHT11' >> build/coldtrack/secrets.h
arduino-cli compile --fqbn esp32:esp32:esp32c3 build/coldtrack            # DHT11
```

Mexeu na infraestrutura: `az bicep build --file infra/main.bicep`. Nunca aplicar o Bicep em
produção sem `az deployment group what-if`.

## Cuidados com produção

- Não renomear a Function App, as rotas nem as chaves de partição do Cosmos DB: as placas
  físicas guardam a URL da API na memória, e a chave de partição não muda depois de criada.
- Módulo `.py` novo na API precisa entrar em `cloud/function/pacote.txt` (o `test_pacote.py`
  avisa).
- Rota nova ou mudada na API entra também em `cloud/function/openapi.json` (o Swagger em
  <https://func-coldtrack-7319.azurewebsites.net/api/docs>); o `test_openapi.py` confere rota a rota.
- Versões das dependências fixadas em `requirements.txt`; subir versão é um commit próprio,
  com os testes passando.

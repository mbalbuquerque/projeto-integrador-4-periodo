# Como contribuir

## Branches

- `main`: branch oficial. Todo push nela que altere `cloud/function/` (ou o próprio workflow)
  **publica a API em produção** (workflow `publicar-api.yml`). Mudanças entram por pull request,
  com os testes verdes.
- Branches de trabalho: criar a partir da `main` (`<tipo>/<assunto>`, por exemplo
  `fix/limite-login`), abrir pull request para a `main` e esperar os testes passarem.
- `everson`: antiga branch de publicação, mantida como reserva. Push nela não publica mais
  depois que a `main` for trazida para ela (até lá, a cópia antiga do workflow que está na
  `everson` ainda publica). Não apagar: o Azure ainda aceita login por OIDC a partir dela, e ela
  é o caminho de volta se a publicação pela `main` falhar.

Antes de editar, atualizar a branch (`git pull`).

O painel web está em outro repositório, [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi),
com fluxo igual (ver o `CONTRIBUTING.md` de lá).

O login do GitHub Actions no Azure é aceito só para as branches `main` e `everson` deste
repositório (ver [`infra/README.md`](infra/README.md)); push em outra branch roda os testes, mas não
publica.

### Revisão de PRs

Everson é o revisor designado da equipe: todo PR é revisado por ele antes do merge (comentário ou aprovação no PR). Vale a partir de 23/11/2026; os PRs anteriores foram mergeados sem revisão formal.

### Proteção da `main`

A `main` deve exigir pull request e os testes verdes antes do merge. Só um administrador do
repositório consegue ligar isso (para quem tem só permissão de escrita a API responde 404).
Comando, rodado por um administrador:

```bash
gh api -X PUT repos/mbalbuquerque/projeto-integrador-4-periodo/branches/main/protection --input - <<'EOF'
{"required_status_checks":{"strict":true,"contexts":["API (lint, testes de contrato e segurança)","Firmware (testes unitários C++ e compilação ESP32-C3)","Imagem Docker da API (build)"]},
 "enforce_admins":false,
 "required_pull_request_reviews":{"required_approving_review_count":0},
 "restrictions":null}
EOF
```

Estado em 23/11/2026: proteção da `main` ativa nos dois repositórios (regra de repositório do GitHub, criada em 23/11/2026).

Os nomes em `contexts` são os jobs do `testes.yml`; se um job for renomeado, a lista precisa
acompanhar. O mesmo vale para o [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi)
(comando no `CONTRIBUTING.md` de lá).

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

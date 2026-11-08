# Infraestrutura (Azure)

`main.bicep` descreve o ambiente que **já existe** no Azure. Ele serve de documentação
versionada e de ponto de partida para recriar o ambiente em outra assinatura. Os valores
padrão dos parâmetros são os nomes e as configurações de produção, levantados com consultas
somente leitura da Azure CLI.

> **Nunca aplicar sobre produção sem `what-if`.** O bloco `appSettings` da Function App
> substitui todas as app settings de uma vez, e as connection strings são recalculadas a
> partir das chaves dos recursos. Um deploy sem conferência pode trocar segredos, derrubar a
> API e, com ela, os sensores em campo.

## Ambiente atual

Assinatura *Azure for Students*, grupo `rg-coldtrack`, região Brazil South.

| recurso | nome | configuração |
|---|---|---|
| Function App (Linux) | `func-coldtrack-7319` | Flex Consumption (plano `ASP-rgcoldtrack-5b46`, FC1), Python 3.11, 2048 MB por instância, até 100 instâncias |
| Storage da função | `stcoldtrack7319` | StorageV2, Standard_LRS, TLS 1.2; guarda `AzureWebJobsStorage` e o pacote publicado (container `app-package-funccoldtrack7319-8454393`) |
| Application Insights | `func-coldtrack-7319` | baseado em workspace (Log Analytics no grupo padrão da assinatura), retenção de 90 dias |
| Cosmos DB for NoSQL | `cosmos-coldtrack-7319` | free tier, consistência Session, uma região, 1000 RU/s compartilhadas no banco |
| Storage do painel | `stcoldtrackweb7319` | site estático (`$web`) em `https://stcoldtrackweb7319.z15.web.core.windows.net` |

### Banco `coldtrack`

| container | chave de partição |
|---|---|
| `empresas` | `/id` |
| `usuarios` | `/id` |
| `veiculos` | `/id` |
| `dispositivos` | `/id` |
| `viagens` | `/id` |
| `leituras` | `/deviceId` |

A chave de partição não muda depois que o container é criado; trocar exige criar outro
container e copiar os dados.

### App settings da Function App

Só os nomes ficam no repositório. Os valores ficam no Azure.

| nome | origem no `main.bicep` | uso |
|---|---|---|
| `AzureWebJobsStorage` | chave da `stcoldtrack7319` | runtime do Functions |
| `DEPLOYMENT_STORAGE_CONNECTION_STRING` | chave da `stcoldtrack7319` | leitura do pacote publicado (Flex Consumption) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Application Insights | logs e métricas |
| `COSMOS_CONNECTION` | chave do Cosmos DB | acesso ao banco |
| `COSMOS_DATABASE` | `coldtrack` | nome do banco |
| `COSMOS_CONTAINER` | `leituras` | container padrão das leituras |
| `TEMP_NORMAL_MAX`, `TEMP_ATENCAO_MAX` | `15`, `20` | legado: o código atual não lê; as faixas vêm de `PERFIS_CARGA` em `contrato.py` |
| `JWT_SECRET` | parâmetro `@secure()` | assinatura dos tokens do painel |

### CORS da API

`http://127.0.0.1:5500`, `http://localhost:5500` (painel rodando localmente) e
`https://stcoldtrackweb7319.z15.web.core.windows.net` (painel publicado).

### Pontos de atenção

- `httpsOnly` está `false` na Function App. Os sensores e o painel já usam HTTPS; ligar
  exige confirmar antes que nenhuma placa grava a URL com `http://`.
- O site estático não é uma propriedade do ARM; foi ligado pela CLI
  (`az storage blob service-properties update --static-website --index-document index.html`).
- A URL da API (`func-coldtrack-7319.azurewebsites.net`) está gravada na memória das placas
  físicas. Renomear a Function App deixa as placas sem destino.

## Validar e conferir

```bash
az bicep build --file infra/main.bicep

# Simulação contra produção (não altera nada). O JWT_SECRET deve ser o mesmo de produção,
# senão o what-if mostra troca e todos os logins caem se alguém aplicar.
az deployment group what-if -g rg-coldtrack \
  --template-file infra/main.bicep \
  --parameters logAnalyticsWorkspaceId=<id do workspace> jwtSecret=<segredo>
```

Aplicar (`az deployment group create`) só depois de ler o `what-if` inteiro e com a equipe
de acordo. Para criar um ambiente novo, passar outros nomes nos parâmetros e outro grupo.

## Publicação pelo GitHub Actions (OIDC)

O workflow `.github/workflows/publicar-api.yml` entra no Azure por OIDC, sem senha guardada:

1. Existe um registro de aplicativo no Entra ID (`coldtrack-github-deploy`) com papel
   **Contributor** apenas no grupo `rg-coldtrack`.
2. Esse aplicativo tem uma credencial federada com emissor
   `https://token.actions.githubusercontent.com`, público `api://AzureADTokenExchange` e
   *subject* restrito à branch `everson` deste repositório
   (`repo:<dono>/projeto-integrador-4-periodo:ref:refs/heads/everson`, no formato com os IDs
   do GitHub).
3. Os secrets do repositório `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` e
   `AZURE_SUBSCRIPTION_ID` só dizem **qual** identidade usar; não são senhas.
4. Na execução, o GitHub emite um token assinado para o job, o `azure/login` troca esse
   token por um acesso ao Azure e o job publica o pacote.

Consequência: um push em outra branch (inclusive `main`) não consegue publicar. Para
publicar a partir de outra branch é preciso criar outra credencial federada com o
*subject* dessa branch.

O painel (repositório Front-End-pi) usa o mesmo aplicativo com uma segunda credencial
federada, também presa à branch `everson` daquele repositório.

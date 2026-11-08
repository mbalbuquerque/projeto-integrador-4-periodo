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
| Azure OpenAI | `aoai-coldtrack-7319` | S0, acesso só por Entra ID (chave de API desligada); deploys `gpt-4.1-mini` (versão 2025-04-14) e `text-embedding-3-small` (versão 1), GlobalStandard, 20 mil tokens por minuto cada |
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
| `limites` | `/id` (TTL ligado, padrão de 2 dias; sem índice) |

O container `limites` guarda os contadores dos limites de uso (falhas de login por IP,
perguntas por minuto e cotas diárias do `/chat` e do `/assistente`), somados entre todas as
instâncias da Function. Cada contador some sozinho pelo TTL quando a janela acaba, e o id
é um hash: IP e e-mail não ficam gravados. Se o container não existir, a API conta na
memória de cada instância e avisa uma vez no log. Ele usa a vazão compartilhada do banco
(1000 RU/s, free tier), sem RU próprias. Criação (uma vez, fora do `main.bicep`):

```bash
az cosmosdb sql container create -g rg-coldtrack -a cosmos-coldtrack-7319 -d coldtrack   -n limites -p /id --ttl 172800   --idx '{"indexingMode":"consistent","automatic":true,"includedPaths":[],"excludedPaths":[{"path":"/*"}]}'
```

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
| `LIMITES_CONTAINER` | (não definida: vale `limites`) | container dos contadores dos limites de uso |
| `TEMP_NORMAL_MAX`, `TEMP_ATENCAO_MAX` | `15`, `20` | legado: o código atual não lê; as faixas vêm de `PERFIS_CARGA` em `contrato.py` |
| `JWT_SECRET` | parâmetro `@secure()` | assinatura dos tokens do painel |
| `AOAI_ENDPOINT` | endpoint da `aoai-coldtrack-7319` | chat do site |
| `AOAI_DEPLOY_CHAT` | `gpt-4.1-mini` | deploy que responde o chat |
| `AOAI_DEPLOY_EMBED` | `text-embedding-3-small` | deploy da busca na base do chat |
| `AOAI_API_VERSION` | `2024-10-21` | versão da API do Azure OpenAI |

`AOAI_KEY` não existe em produção: o código só usa chave se ela estiver definida, e o recurso
recusa chave. Sem ela, a API entra no Azure OpenAI com a identidade gerenciada.

### Identidade e papéis

A Function App tem identidade gerenciada atribuída pelo sistema, com o papel
**Cognitive Services OpenAI User** na conta `aoai-coldtrack-7319` (só chama os modelos, não
altera o recurso). Atribuir papel exige permissão de *Owner* ou *User Access Administrator*:
o aplicativo do GitHub Actions (Contributor) não consegue, então o papel foi atribuído à mão:

```bash
az functionapp identity assign -g rg-coldtrack -n func-coldtrack-7319
az role assignment create --role "Cognitive Services OpenAI User" \
  --assignee-object-id <principalId da Function> --assignee-principal-type ServicePrincipal \
  --scope $(az cognitiveservices account show -g rg-coldtrack -n aoai-coldtrack-7319 --query id -o tsv)
```

Quem roda `scripts/gerar_base_chat.py` na própria máquina precisa do mesmo papel para a
conta do `az login`.

### CORS da API

Só `https://stcoldtrackweb7319.z15.web.core.windows.net` (painel publicado). As origens de
desenvolvimento (`localhost:5500`) foram tiradas de produção: para testar o painel na
máquina, rodar a API local (`func start`) e apontar o painel para ela.

### Pontos de atenção

- O chat público tem custo por uso no Azure OpenAI (sai do crédito da assinatura). A rota
  limita 10 perguntas por minuto por IP e 2000 por dia no total; o assistente do painel,
  15 por minuto por usuário e 300 por dia por empresa. A cota dos deploys (20 mil tokens
  por minuto) é o teto. Cota esgotada vira `503` e o site cai no FAQ.
- `httpsOnly` está `true` na Function App (ligado em produção): chamada por `http://` é
  redirecionada para HTTPS. Os sensores e o painel já usavam HTTPS.
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

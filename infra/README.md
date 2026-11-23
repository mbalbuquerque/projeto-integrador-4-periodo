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

## Custo mensal estimado

Estimativa feita em 16/11/2026 com os recursos reais do grupo `rg-coldtrack`, o uso dos
últimos 30 dias (17/10 a 16/11/2026) e os preços públicos da Azure Retail Prices API
(região `brazilsouth`, moeda USD). Cotação usada: **US$ 1 = R$ 5,7897** (AwesomeAPI, compra,
16/11/2026). É uma estimativa de ordem de grandeza, não uma fatura.

### Recursos e SKUs encontrados

| recurso | SKU / configuração real |
|---|---|
| Function App | Flex Consumption (FC1), Python 3.11, 2048 MB, sem instância sempre pronta |
| Cosmos DB | conta com free tier, vazão provisionada de 1000 RU/s compartilhada no banco (não é serverless), uma região |
| Storage da função e do painel | 2 contas StorageV2, Standard_LRS, camada Hot |
| Application Insights | baseado em workspace do Log Analytics, retenção de 90 dias |
| Azure OpenAI | S0; `gpt-4.1-mini` e `text-embedding-3-small`, GlobalStandard |

### Uso medido nos últimos 30 dias (piloto)

Medido com `az monitor metrics list` (Function, Cosmos, Storage, Azure OpenAI) e com consulta
à tabela `Usage` do workspace (Log Analytics):

| item | medido |
|---|---|
| Execuções da Function | 3.039 (3.535 GB-s de execução) |
| Cosmos DB | 43.628 requisições, 15.267 RU no mês; 3,4 MB de dados |
| Storage (função + painel) | 23.167 transações; 76 MB armazenados |
| Log Analytics | 68,8 MB ingeridos (traces 52 MB, métricas 11 MB, contadores 2 MB, requisições 4 MB) |
| Azure OpenAI | 183 requisições; 171 mil tokens de entrada, 2,5 mil de saída |

`az consumption usage list` respondeu, mas com custo e quantidade vazios para todos os itens
(a assinatura Azure for Students não expõe valores de cobrança por essa rota). Por isso não há
comparação com fatura real: os valores abaixo são calculados, não lidos da cobrança.

### Preços unitários usados (USD, Brazil South)

| item | preço | franquia gratuita |
|---|---|---|
| Flex Consumption, execução sob demanda | 0,000037 por GB-s | 100.000 GB-s por mês |
| Flex Consumption, execuções | 0,40 por milhão | 250.000 por mês |
| Cosmos DB provisionado | 0,012 por 100 RU/s por hora | free tier: 1000 RU/s e 25 GB |
| Cosmos DB armazenamento | 0,375 por GB por mês | (dentro do free tier) |
| Cosmos DB serverless (alternativa) | 0,375 por milhão de RU | nenhuma |
| Blob Hot LRS, armazenamento | 0,0326 por GB por mês | nenhuma |
| Blob Hot LRS, leitura / escrita | 0,0056 / 0,07 por 10 mil operações | nenhuma |
| Log Analytics, ingestão | 4,60 por GB | 5 GB por mês |
| `gpt-4.1-mini` GlobalStandard | entrada 0,0004 e saída 0,0016 por mil tokens | nenhuma |
| `text-embedding-3-small` | não retornado pela API para a região; preço de tabela global na ordem de US$ 0,02 por milhão de tokens, não conferido na API (desprezível aqui) | nenhuma |

### Hoje (piloto)

| recurso | SKU | uso (30 dias) | US$/mês | R$/mês |
|---|---|---|---|---|
| Function App | Flex Consumption | 3.039 execuções; 3.535 GB-s | 0,00 (dentro da franquia) | 0,00 |
| Cosmos DB | free tier, 1000 RU/s | 15.267 RU; 3,4 MB | 0,00 (free tier) | 0,00 |
| Storage (2 contas) | Standard_LRS Hot | 76 MB; 23 mil transações | 0,02 | 0,09 |
| Application Insights / Log Analytics | workspace, 90 dias | 0,069 GB ingeridos | 0,00 (menos de 5 GB) | 0,00 |
| Azure OpenAI | gpt-4.1-mini + embedding | 171 mil tokens de entrada, 2,5 mil de saída | 0,07 | 0,42 |
| **Total** | | | **cerca de 0,09** | **cerca de 0,50** |

O custo do piloto é praticamente zero porque o uso cabe nas franquias da Function, do free tier
do Cosmos e dos 5 GB do Log Analytics. O gasto real é o do Azure OpenAI, e sai do crédito da
assinatura.

### Uma transportadora com 10 caminhões

Premissas (todas declaradas, nenhuma medida em campo):

- 10 sensores, um por caminhão, ligados 24 h por dia, 30 dias, uma leitura a cada 20 s:
  10 x 129.600 = **1.296.000 chamadas** a `POST /telemetria` por mês (sem perdas nem reenvio).
- Painel: 5 usuários com a tela aberta 8 h por dia, 22 dias, atualizando a cada 20 s, o que
  soma cerca de 300 mil chamadas. Total de **cerca de 1,6 milhão de execuções** por mês.
- Consumo da Function e volume de logs por execução iguais à média medida no piloto
  (1,16 GB-s e 22,6 KB por execução). É uma estimativa conservadora: o piloto inclui chamadas
  longas de IA e testes, e a telemetria é mais curta, então o valor real tende a ser menor.
- Cosmos: cerca de 12 RU por telemetria (leitura do sensor, consulta do veículo e gravação),
  16 milhões de RU por mês, média de 6 RU/s, muito abaixo dos 1000 RU/s. Cada leitura ocupa
  cerca de 0,5 a 1 KB com índice, ou seja, cerca de 1 GB novo por mês; o container `leituras`
  não tem TTL, então os 25 GB do free tier duram mais de 2 anos. O valor de 12 RU é uma
  suposição, não foi medido.
- Storage: transações proporcionais às execuções (8,5 milhões por mês), todas a preço de leitura.
- Azure OpenAI: 200 perguntas por dia ao assistente do painel (6.000 por mês, abaixo do teto de
  300 por dia por empresa), com 5.000 tokens de entrada e 300 de saída cada. O chat do site
  fica no nível do piloto.
- Os 5 GB gratuitos do Log Analytics são por assinatura (outros usos dela os consomem) e a
  retenção de 90 dias das tabelas do Application Insights não tem cobrança extra.

| recurso | SKU | uso estimado | US$/mês | R$/mês |
|---|---|---|---|---|
| Function App | Flex Consumption | 1,6 milhão de execuções (US$ 0,54 acima da franquia) e 1,86 milhão de GB-s (US$ 65,16 acima da franquia) | 65,70 | 380 |
| Cosmos DB | free tier, 1000 RU/s | 16 milhões de RU; cerca de 1 GB | 0,00 | 0 |
| Storage (2 contas) | Standard_LRS Hot | 8,5 milhões de transações; menos de 1 GB | 4,78 | 28 |
| Application Insights / Log Analytics | workspace, 90 dias | 36,2 GB ingeridos (31,2 GB acima da franquia) | 143,62 | 832 |
| Azure OpenAI | gpt-4.1-mini + embedding | 30 milhões de tokens de entrada, 1,8 milhão de saída | 14,88 | 86 |
| **Total** | | | **cerca de 229** | **cerca de 1.326** |

Leitura do resultado:

- **Log Analytics é o maior item e é evitável.** No piloto, mais de 99% dos traces são de
  nível Information (linhas de início e fim de cada execução do host). Subir o nível de log da
  Function para Warning (`logging.logLevel` no `host.json`) tira cerca de 60% do volume
  ingerido (de 68,8 para 27,1 MB no piloto), o que leva o item a cerca de US$ 43 e o total a
  cerca de US$ 128 (R$ 741). Não foi aplicado: mexer em `cloud/function/` na `main`
  publica a API em produção.
- **Function:** o valor usa a média medida e funciona como teto; com execuções curtas de
  telemetria o gasto deve ficar abaixo. Medir com sensores ligados por alguns dias melhora a
  estimativa.
- **Cosmos sem free tier:** o free tier vale para uma conta por assinatura. Em outra assinatura,
  1000 RU/s provisionados custam 10 x 0,012 x 730 h = US$ 87,60 por mês (R$ 507). Como o uso
  estimado é de 6 RU/s, o Cosmos serverless (US$ 0,375 por milhão de RU, cerca de US$ 6 por
  mês neste volume) seria bem mais barato, mas exige criar outra conta: o modo da conta não
  muda depois de criada.
- **Azure OpenAI:** os tetos de uso da API (ver `docs/seguranca.md`) limitam o gasto: 300
  perguntas por dia por empresa no assistente e 2000 por dia no chat do site. A cota de
  tokens por minuto dos deploys limita a vazão, não o gasto.
- Fora desta estimativa: tráfego de saída (a API devolve JSON pequeno e a Azure dá 100 GB
  gratuitos por mês), domínio próprio, suporte pago, backup além do periódico padrão do
  Cosmos e impostos (IOF e outros, que se somam na fatura em reais).
- O crédito do Azure for Students cobre o piloto. Para uso real por uma transportadora é
  necessária assinatura paga, e os valores acima passam a ser cobrados.

## Contêiner e compose (testado no CI)

`infra/Dockerfile` empacota a API (imagem oficial de Azure Functions, Python 3.11) e
`infra/docker-compose.yml` sobe a API junto com o emulador oficial do Cosmos DB para Linux
(`mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-preview`, em HTTP). Para
desenvolvimento: `cp .env.example .env` (os valores de exemplo já apontam para o emulador),
`docker compose -f infra/docker-compose.yml up --build` e, uma vez, `python infra/ci/preparar_banco.py`
(cria o banco, os containers e um usuário de teste). A API fica em `http://localhost:7071/api`.

O workflow `Compose e ZAP` (`.github/workflows/compose-zap.yml`) executa esse mesmo compose no
runner do GitHub Actions, sem segredo real (a chave do emulador é pública e a senha do usuário
de teste é fictícia). Sem o emulador, `/api/health` responde `503` com `"banco": "indisponivel"`,
porque a sonda consulta o Cosmos; com ele, responde `200`. Os tempos ficam no artefato
`compose-e-zap` (`resultados/reinicio.txt`, `resultados/saude.txt`).

Medição de 16/11/2026 (execução do PR, runner `ubuntu-latest`; valores de uma execução, não média):

| verificação | resultado |
|---|---|
| `docker compose up -d --build` até `/api/health` responder 200 | 60,6 s (imagem e emulador baixados do zero) |
| `healthcheck` do contêiner da API | `healthy` logo depois da subida |
| Queda do processo (SIGKILL no PID 1 do contêiner, como o OOM killer) com `restart: unless-stopped` | volta a responder 200 em **4,4 s**; contagem de reinícios 0 para 1; `healthy` 2,1 s depois |
| `docker kill` | **não reinicia**: o Docker trata como parada pedida pelo operador (estado `exited` 30 s depois, 0 reinícios novos) |
| `docker stop` | não reinicia, como esperado em `unless-stopped`; `docker start` volta em 3,9 s |

Conclusão: a política `unless-stopped` recupera a API de uma queda do processo em poucos
segundos, mas não de uma parada manual. A primeira medição desse CI usou `docker kill` e ficou 180 s
sem reinício, o que revelou essa diferença. Em produção (Function App), a recuperação é da plataforma
Azure; o compose vale para desenvolvimento e para a demonstração em contêiner.

## Backup e restauração (R8)

Há duas camadas, com limites diferentes.

### 1. Backup periódico gerenciado (Azure)

A conta usa `backupPolicy: Periodic` (`infra/main.bicep`). Valores lidos da conta com
`az cosmosdb show` em 16/11/2026:

| parâmetro | valor |
|---|---|
| intervalo entre cópias | 240 min (4 h) |
| retenção | 8 h (duas cópias) |
| redundância do armazenamento do backup | Geo |

- **RPO**: até 4 h de dados perdidos.
- **RTO**: não mensurável por nós. No modo periódico a restauração é feita pelo suporte da
  Azure, por chamado, para uma conta nova; não existe comando para o cliente. Por isso essa
  camada **não foi testada**, e o tempo de atendimento do chamado é desconhecido.
- **Limite importante**: com 8 h de retenção, um apagamento ou corrupção percebido depois
  de 8 h não pode ser desfeito por essa camada. O chamado precisa ser aberto dentro da
  janela.
- Esta política não foi alterada. Mudar a retenção ou migrar para o modo contínuo (que
  permite restauração para um instante, feita pelo próprio cliente) tem custo e é decisão
  da equipe.

### 2. Backup lógico (testado)

Exporta cada container para um arquivo JSONL (um documento por linha, sem as propriedades de
sistema do Cosmos) e um `manifesto.json` com data, banco, contagem, chave de partição e TTL de
cada container. Os scripts ficam em `infra/backup/` e dependem só de `azure-cosmos`.

**Exportar** (só leitura; use a chave somente leitura da conta):

```bash
export COSMOS_ENDPOINT=$(az cosmosdb show -g rg-coldtrack -n cosmos-coldtrack-7319 --query documentEndpoint -o tsv)
export COSMOS_KEY=$(az cosmosdb keys list -g rg-coldtrack -n cosmos-coldtrack-7319 \
  --type read-only-keys --query primaryReadonlyMasterKey -o tsv)
python infra/backup/exportar.py ~/backups-coldtrack/$(date +%F)
```

O export contém dado real (e-mails, hashes de senha, leituras). Gravar **fora do
repositório** e com acesso restrito; o `.gitignore` bloqueia `*.jsonl`, `manifesto.json` e
`backups-coldtrack/` como segunda barreira. Containers com TTL (`limites`) são exportados
como estão; seus contadores expiram sozinhos e não precisam ser preservados (use
`--excluir limites` para pulá-los).

**Restaurar** (nunca em produção):

```bash
export DEST_ENDPOINT=<endpoint da conta de teste ou do emulador>
export DEST_KEY=<chave do destino>
python infra/backup/restaurar.py ~/backups-coldtrack/2026-11-16 --banco coldtrack-restaurado
```

O script recusa qualquer endpoint `*.documents.azure.com` antes de abrir conexão. Cria o
banco e os containers com a chave de partição e o TTL do manifesto, grava com `upsert` (pode
repetir) e compara, container a container, a contagem esperada com a restaurada; sai com
código 1 se houver divergência.

**Procedimento de recuperação** (perda de dados em produção):

1. Congelar escritas (parar a Function App ou tirar a API do ar) para não misturar dado novo.
2. Pegar o export mais recente e conferir o `manifesto.json` (data e contagens).
3. Criar uma conta Cosmos nova (ou o banco `coldtrack-restaurado` em conta de teste) e rodar
   `restaurar.py` contra ela. Conferir a saída: todos os containers `[ok]`.
4. Apontar `COSMOS_CONNECTION` da Function App para a conta restaurada, ou copiar de volta só os
   documentos necessários. Trocar de conta exige pôr de novo os papéis e as configurações da
   conta original.
5. Conferir `GET /api/health` (`banco: ok`) e fazer um login.

**Frequência sugerida**: um export por dia (RPO de até 24 h), guardado em local com retenção
maior que as 8 h do periódico. Não há agendamento automático criado; rodar manualmente ou por
um job da equipe, com a chave somente leitura.

**Medições**

| item | resultado |
|---|---|
| Export real de produção (16/11/2026, chave somente leitura) | 4.041 documentos em 7 containers, cerca de 1 MB, **8,1 s** (de uma máquina local) |
| Contagens por container | `leituras` 4.025; `usuarios` 5; `empresas` 3; `limites` 3; `veiculos` 1; `dispositivos` 1; `viagens` 0 |
| Export real de produção (23/11/2026, chave somente leitura) | 16.105 documentos em 5 containers (`leituras` 16.100; `empresas` 3; `veiculos` 1; `dispositivos` 1; `viagens` 0), **9,4 s**; `usuarios` e `limites` ficaram de fora de propósito (e-mail e hash de senha) |
| Conferência do export real e ensaio de restauração em memória (23/11/2026) | `verificar_export.py`: contagem do manifesto igual à do arquivo em todos os containers, nenhum documento sem `id` ou chave de partição, nenhum `id` repetido na partição; `restaurar.restaurar` rodou duas vezes contra um Cosmos falso em memória, 16.105 de 16.105 documentos restaurados, as duas rodadas em menos de 0,1 s, a segunda sem criar duplicata (idempotente) |
| Restauração do export real num Cosmos de verdade (23/11/2026) | **executada**: export de produção (16.105 documentos) restaurado numa conta Cosmos de teste (serverless, grupo de recursos próprio), com `restaurar.restaurar` chamado direto porque o `restaurar.py` recusa contas `*.documents.azure.com`, depois de conferir que o destino não era a conta de produção. Contagens iguais em todos os containers (leituras 16.100, empresas 3, veículos 1, dispositivos 1, viagens 0), duração de 782 s; a conta de teste e o grupo de recursos foram apagados e a produção não foi tocada. O backup periódico gerenciado do Cosmos segue sem teste, por só restaurar por chamado ao suporte |
| Restauração sintética no emulador (CI) | PR #74: banco sintético de 63 documentos em 4 containers exportado e restaurado em outro banco, contagens iguais, leitura de um documento por container e chave de partição e TTL recriados; execução inteira dos testes em cerca de 1 s (o emulador leva cerca de 25 s para subir) |

RTO do backup lógico: tempo de recriar o destino mais o da restauração (no CI, em
runner pequeno, o volume sintético restaurou em menos de 1 s); para o volume atual fica na ordem de minutos, e cresce de forma linear com o
número de documentos (o `upsert` documento a documento é o gargalo).

**Conferir um export sem Cosmos**: `python infra/backup/verificar_export.py <pasta-do-export>` confere o manifesto com os arquivos, procura documento sem `id` ou chave de partição e `id` repetido, e ensaia a restauração duas vezes em memória (sem rede). Sai com 1 se algo divergir. Testes em `infra/backup/test_verificar_export.py`, que o job `Backup logico` já roda.

**Teste no CI**: o workflow `.github/workflows/backup-logico.yml` sobe o emulador oficial do
Cosmos DB, cria um banco sintético com os mesmos containers e chaves de partição do real,
exporta, restaura em outro banco e confere contagens, um documento por container (leitura por
id e chave de partição), a chave de partição e o TTL recriados. Também roda os dois scripts
pela linha de comando e verifica que `restaurar.py` recusa um endpoint Azure. Os testes das
funções ficam em `infra/backup/test_backup.py` (`python -m pytest infra/backup`).

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
   *subject* restrito a uma branch deste repositório. São duas credenciais:
   `gh-projeto-integrador-4-periodo-main` (branch `main`, a que publica) e
   `gh-projeto-integrador-4-periodo-everson` (branch `everson`, reserva). O *subject* usa o
   formato com os IDs do GitHub:
   `repo:<dono>@<id do dono>/projeto-integrador-4-periodo@<id do repo>:ref:refs/heads/main`.
3. Os secrets do repositório `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` e
   `AZURE_SUBSCRIPTION_ID` só dizem **qual** identidade usar; não são senhas.
4. Na execução, o GitHub emite um token assinado para o job, o `azure/login` troca esse
   token por um acesso ao Azure e o job publica o pacote.

O workflow dispara em push na `main` (e manualmente, por `workflow_dispatch`). Um push em
outra branch não consegue publicar, porque o Azure recusa o token. Para publicar a partir de
outra branch é preciso criar outra credencial federada com o *subject* dessa branch, copiando o
formato de uma existente:

```bash
az ad app federated-credential list --id <AZURE_CLIENT_ID> -o table
az ad app federated-credential create --id <AZURE_CLIENT_ID> --parameters credencial.json
```

O painel (repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi)) usa o mesmo
aplicativo, com as credenciais `gh-Front-End-pi-main` e `gh-Front-End-pi-everson`.

A `everson` dos dois repositórios deixou de disparar a publicação, mas a credencial dela foi
mantida como reserva: se a publicação pela `main` falhar, basta voltar o gatilho do workflow
para a `everson`. Por isso a `everson` não deve ser apagada enquanto essa credencial existir.

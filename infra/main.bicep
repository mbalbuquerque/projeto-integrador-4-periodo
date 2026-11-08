// ColdTrack: descricao em Bicep do ambiente que ja existe no grupo rg-coldtrack.
//
// Este arquivo documenta o ambiente de producao. NUNCA aplicar sobre ele sem antes
// rodar `az deployment group what-if` e ler o resultado (ver infra/README.md).
// Os valores padrao dos parametros sao os nomes e as configuracoes reais.
//
// Nenhum segredo fica aqui: as connection strings sao calculadas no deploy a partir
// das chaves dos proprios recursos e o JWT_SECRET entra como parametro seguro.

targetScope = 'resourceGroup'

@description('Regiao de todos os recursos.')
param location string = 'brazilsouth'

@description('Function App da API (a URL esta gravada nas placas fisicas: nao trocar).')
param functionAppName string = 'func-coldtrack-7319'

@description('Plano Flex Consumption da Function App.')
param planName string = 'ASP-rgcoldtrack-5b46'

@description('Storage da Function App (AzureWebJobsStorage e pacote do deploy).')
param functionStorageName string = 'stcoldtrack7319'

@description('Container de blob onde o Flex Consumption guarda o pacote publicado.')
param deploymentContainerName string = 'app-package-funccoldtrack7319-8454393'

@description('Storage com site estatico (container $web) que serve o painel.')
param webStorageName string = 'stcoldtrackweb7319'

@description('Application Insights da Function App.')
param appInsightsName string = 'func-coldtrack-7319'

@description('ID do workspace do Log Analytics ligado ao Application Insights (fica em outro grupo).')
param logAnalyticsWorkspaceId string

@description('Conta do Cosmos DB for NoSQL (free tier).')
param cosmosAccountName string = 'cosmos-coldtrack-7319'

@description('Banco do Cosmos DB.')
param cosmosDatabaseName string = 'coldtrack'

@description('Vazao compartilhada do banco (1000 RU/s cabe no free tier).')
param cosmosThroughput int = 1000

@description('Segredo de assinatura dos tokens do painel. Vem de Key Vault ou de parametro seguro.')
@secure()
param jwtSecret string

@description('Origens liberadas no CORS da API.')
param corsOrigins array = [
  'http://127.0.0.1:5500'
  'http://localhost:5500'
  'https://${webStorageName}.z15.web.${environment().suffixes.storage}'
]

@description('Em producao hoje esta false; os sensores e o painel ja chamam a API por HTTPS.')
param httpsOnly bool = false

// Containers do banco e suas chaves de particao (nao podem mudar depois de criados).
var containers = [
  { name: 'empresas', pk: '/id' }
  { name: 'usuarios', pk: '/id' }
  { name: 'veiculos', pk: '/id' }
  { name: 'dispositivos', pk: '/id' }
  { name: 'viagens', pk: '/id' }
  { name: 'leituras', pk: '/deviceId' }
]

// ---------------------------------------------------------------- Storage

resource functionStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: functionStorageName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

resource functionBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: functionStorage
  name: 'default'
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: functionBlob
  name: deploymentContainerName
}

// Site estatico: o "static website" (container $web, documento index.html) e uma
// propriedade do servico de blob que o ARM nao expoe. Foi ligado pela CLI
// (az storage blob service-properties update --static-website --index-document index.html)
// e o conteudo e publicado pelo repositorio do painel (Front-End-pi).
resource webStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: webStorageName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

// ---------------------------------------------------------------- Monitoramento

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspaceId
    RetentionInDays: 90
  }
}

// ---------------------------------------------------------------- Cosmos DB

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: true
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [
      { locationName: location, failoverPriority: 0, isZoneRedundant: false }
    ]
    minimalTlsVersion: 'Tls12'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
    backupPolicy: { type: 'Periodic' }
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: cosmosDatabaseName
  properties: {
    resource: { id: cosmosDatabaseName }
    options: { throughput: cosmosThroughput }
  }
}

resource sqlContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [
  for c in containers: {
    parent: database
    name: c.name
    properties: {
      resource: {
        id: c.name
        partitionKey: { paths: [ c.pk ], kind: 'Hash' }
        indexingPolicy: { indexingMode: 'consistent' }
      }
    }
  }
]

// ---------------------------------------------------------------- Function App

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  kind: 'functionapp'
  sku: { name: 'FC1', tier: 'FlexConsumption' }
  properties: { reserved: true }
}

var functionStorageConnection = 'DefaultEndpointsProtocol=https;AccountName=${functionStorage.name};AccountKey=${functionStorage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: httpsOnly
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${functionStorage.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'StorageAccountConnectionString'
            storageAccountConnectionStringName: 'DEPLOYMENT_STORAGE_CONNECTION_STRING'
          }
        }
      }
      runtime: { name: 'python', version: '3.11' }
      scaleAndConcurrency: {
        instanceMemoryMB: 2048
        maximumInstanceCount: 100
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      ftpsState: 'FtpsOnly'
      cors: {
        allowedOrigins: corsOrigins
        supportCredentials: false
      }
      // Atencao: aplicar este bloco SUBSTITUI todas as app settings da Function App.
      appSettings: [
        { name: 'AzureWebJobsStorage', value: functionStorageConnection }
        { name: 'DEPLOYMENT_STORAGE_CONNECTION_STRING', value: functionStorageConnection }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'COSMOS_CONNECTION', value: cosmos.listConnectionStrings().connectionStrings[0].connectionString }
        { name: 'COSMOS_DATABASE', value: cosmosDatabaseName }
        { name: 'COSMOS_CONTAINER', value: 'leituras' }
        // TEMP_NORMAL_MAX e TEMP_ATENCAO_MAX existem em producao, mas o codigo atual nao
        // os le (as faixas vem de PERFIS_CARGA em contrato.py). Ficam aqui para o
        // what-if nao acusar remocao.
        { name: 'TEMP_NORMAL_MAX', value: '15' }
        { name: 'TEMP_ATENCAO_MAX', value: '20' }
        { name: 'JWT_SECRET', value: jwtSecret }
      ]
    }
  }
  dependsOn: [ deploymentContainer ]
}

output apiBaseUrl string = 'https://${functionApp.properties.defaultHostName}/api'
output webEndpoint string = webStorage.properties.primaryEndpoints.web
output cosmosEndpoint string = cosmos.properties.documentEndpoint

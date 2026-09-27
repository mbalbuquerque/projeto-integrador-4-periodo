# ColdTrack — Stack Técnica

Documento de referência da arquitetura do ColdTrack: o que cada parte faz, em que tecnologia
foi feita, onde roda, como os dados circulam e como o sistema é publicado. Situação em 26/09/2026.

## 1. Visão geral

O ColdTrack monitora a temperatura e a umidade dentro do baú refrigerado de caminhões que levam
frutas do Vale do São Francisco aos portos. Um sensor instalado no baú mede as condições a cada
20 segundos e envia as leituras pela internet para a nuvem. Um painel web mostra a situação
atual da carga, o histórico, os alertas e os relatórios.

![Figura 1 — Arquitetura: borda IoT, contrato HTTPS/JSON, serviços Azure e camada de apresentação.](arquitetura.png)

O caminho de uma leitura:

1. O **sensor** (DHT11/DHT22) mede temperatura e umidade.
2. O **ESP32-C3** valida a leitura, classifica a condição da carga e acende o LED correspondente.
3. O ESP32 envia a leitura em **JSON, por HTTPS**, para a **API** no Azure.
4. A API confere o formato, classifica de novo e grava no **banco de dados**.
5. O **painel web**, aberto no navegador, pede os dados à API e desenha as telas.

## 2. Componentes e tecnologias

| Componente | Função | Tecnologia | Onde roda |
|---|---|---|---|
| Firmware | Leitura do sensor, LEDs, envio das leituras, fila sem conexão | C++ (Arduino Framework) | ESP32-C3 no baú (hoje simulado no Wokwi) |
| API (backend) | Recebe e valida leituras, login, cadastros, consulta de dados | Python 3.11 | Azure Functions |
| Banco de dados | Guarda leituras, usuários, veículos e viagens | NoSQL (documentos JSON) | Azure Cosmos DB |
| Painel (frontend) | Dashboard, alertas, relatórios, veículos, viagens, usuários | HTML, CSS e JavaScript (sem framework), PWA | Azure Storage — site estático |
| Análise de dados | Clima da rota e modelo preliminar de risco térmico | Python (Pandas, Matplotlib) | Máquina local; resultado versionado no repositório |
| Testes automáticos | Testes da API e compilação do firmware a cada envio | GitHub Actions | GitHub |

Repositórios:

| Repositório | Conteúdo |
|---|---|
| `projeto-integrador-4-periodo` | Firmware (`sketch.ino`), API (`cloud/function/`), análise (`analise/`), documentação (`docs/`) |
| `Front-End-pi` | Painel web |

## 3. Borda (IoT)

| Item | Detalhe |
|---|---|
| Microcontrolador | ESP32-C3 |
| Sensor | DHT11 na placa física; DHT22 no simulador (escolhido por `DHT_TYPE` no `secrets.h`) |
| Sinalização | LEDs verde (normal), amarelo (atenção) e vermelho (crítico) nos GPIOs 5, 6 e 7 |
| Intervalo | Uma leitura a cada 20 s, com temporização não bloqueante (`millis`) |
| Conexão | Wi-Fi no protótipo; módulo 4G (A7670SA) com chip na versão final |
| Segurança | HTTPS com verificação do certificado do servidor (raiz DigiCert Global Root G2) |
| Relógio | Sincronizado pela internet (NTP); cada leitura leva o horário da medição |

**Leitura inconsistente (Fail-Fast).** Se o sensor devolve valor inválido (`isnan`), a leitura
não é enviada e o LED vermelho pisca.

**Sem conexão (store-and-forward).** Quando não há internet, a leitura é gravada na memória
flash do ESP32 (até 500 leituras, cerca de 2 h 45 min). Quando a conexão volta, as leituras
guardadas são enviadas da mais antiga para a mais nova, com o horário original da medição.
Assim, um trecho de estrada sem sinal não deixa buraco no histórico.

Formato enviado:

```
POST https://func-coldtrack-7319.azurewebsites.net/api/telemetria
x-functions-key: <chave do dispositivo>
Content-Type: application/json

{"deviceId":"coldtrack-01","temperatura":12.4,"umidade":81.0,"rssi":-58,"medidoEm":1790464605}
```

## 4. Nuvem: serviços do Azure

O Azure é a nuvem da Microsoft: computadores alugados, oferecidos como serviços prontos.
O projeto usa a assinatura **Azure for Students**, região **Brazil South** (São Paulo).
Todos os recursos ficam no grupo de recursos `rg-coldtrack`.

| Serviço | Recurso | Para que serve |
|---|---|---|
| Azure Functions (plano Flex Consumption) | `func-coldtrack-7319` | Roda a API |
| Azure Cosmos DB for NoSQL (camada gratuita) | `cosmos-coldtrack-7319` | Banco de dados |
| Azure Storage — site estático | `stcoldtrackweb7319` | Hospeda o painel web |
| Azure Storage | `stcoldtrack7319` | Armazenamento interno da Function |
| Application Insights | `func-coldtrack-7319` | Logs e erros da API |

### 4.1 Azure Functions (serverless)

No modelo *serverless*, não existe um servidor ligado o tempo todo para administrar. O código é
entregue ao Azure, que executa a função apenas quando chega uma requisição e cobra por
execução. Para o volume do protótipo, o custo fica dentro da cota gratuita.

### 4.2 Azure Cosmos DB (NoSQL)

O Cosmos DB guarda **documentos JSON** em vez de linhas de tabela com colunas fixas. Cada
coleção de documentos é um **container** (equivalente a uma tabela). A escolha combina com
telemetria: muitos registros simples chegando continuamente, no mesmo formato JSON enviado pelo
dispositivo. A **chave de partição** define como os dados são distribuídos: as leituras são
particionadas por dispositivo, então consultar o histórico de um caminhão lê uma única partição.

### 4.3 Site estático no Azure Storage

Os arquivos do painel (HTML, CSS, JavaScript e imagens) ficam em um armazenamento com a opção
de site estático ativada e são servidos por HTTPS. Não há código executando no servidor: o
JavaScript roda no navegador do usuário e busca os dados na API.

O Azure Static Web Apps, alternativa com login pronto, não está disponível nas regiões
liberadas para a assinatura acadêmica; por isso o login foi implementado na própria API.

## 5. Modelo de dados

Banco `coldtrack`, quatro containers:

| Container | Chave de partição | Conteúdo |
|---|---|---|
| `leituras` | `/deviceId` | Uma leitura do sensor por documento |
| `usuarios` | `/id` (e-mail) | Pessoas com acesso ao painel |
| `veiculos` | `/id` (código do veículo) | Frota e o sensor instalado em cada veículo |
| `viagens` | `/id` | Trajetos, com origem, destino, carga, início e fim |

Exemplos de documentos:

```
leituras
{"id":"3660eb0a-…","deviceId":"coldtrack-01","temperatura":24.5,"umidade":80.0,"rssi":null,
 "status":"CRITICO","medidoEm":"2026-09-26T23:36:45+00:00","recebidoEm":"2026-09-26T23:36:46+00:00"}

usuarios
{"id":"gestor@empresa.com","nome":"Gestor","perfil":"gestor","senhaHash":"scrypt$16384$8$1$…"}

veiculos
{"id":"CT-001","tipo":"Caminhão baú refrigerado","deviceId":"coldtrack-01",
 "dispositivo":"ESP32-C3 + DHT11","perfil":"demonstrativo"}

viagens
{"id":"V-DB6E09","veiculo":"CT-001","origem":"Petrolina/PE","destino":"Porto de Suape/PE",
 "carga":"Manga","inicio":"2026-09-26T21:00:00+00:00","fim":null}
```

O formato de cada documento é validado no código da API antes de gravar.

**Classificação da carga** (valores demonstrativos, iguais no firmware, na API e no painel):

| Temperatura | Status |
|---|---|
| até 15 °C | NORMAL |
| acima de 15 °C até 20 °C | ATENCAO |
| acima de 20 °C | CRITICO |

## 6. API

Base: `https://func-coldtrack-7319.azurewebsites.net/api`

| Método e rota | Quem usa | Permissão | Função |
|---|---|---|---|
| `POST /telemetria` | Dispositivo | Chave do dispositivo | Valida, classifica e grava a leitura |
| `POST /login` | Pessoa | Aberta | Troca e-mail e senha por um token de acesso |
| `GET /eu` | Painel | Operador ou gestor | Dados do usuário logado |
| `GET /leituras` | Painel | Operador ou gestor | Leituras, com filtros de período (`horas`) e `status` |
| `GET /veiculos`, `GET /viagens` | Painel | Operador ou gestor | Frota e viagens |
| `POST`, `PUT`, `DELETE` em `/veiculos` e `/viagens` | Painel | Gestor | Cadastro, alteração e remoção |
| `GET`, `POST`, `DELETE` em `/usuarios` | Painel | Gestor | Gestão de usuários |

Respostas de erro: **400** (dado inválido, com a lista de erros), **401** (sem login ou token
inválido), **403** (perfil sem permissão), **404** (não encontrado), **409** (cadastro repetido).

Organização do código (`cloud/function/`):

| Arquivo | Responsabilidade |
|---|---|
| `function_app.py` | Rotas da API e acesso ao banco |
| `contrato.py` | Validação e classificação das leituras |
| `seguranca.py` | Hash de senha e token de acesso |
| `cadastros.py` | Validação de usuários, veículos e viagens |
| `test_contrato.py`, `test_seguranca.py` | 42 testes automatizados |

## 7. Painel web

| Tela | Conteúdo |
|---|---|
| Página inicial | Apresentação do produto e login |
| Dashboard | Leitura atual e gráfico dos últimos 30 minutos com a faixa normal e os limites |
| Alertas | Ocorrências fora da faixa (leituras seguidas agrupadas), com duração e pico |
| Relatórios | Resumo de 24 h ou 7 dias, gráfico, tabela e exportação em CSV |
| Veículos | Situação atual de cada veículo, aviso de sensor sem sinal; cadastro pelo gestor |
| Viagens | Condição da carga do início ao fim de cada trajeto; registro pelo gestor |
| Configurações | Faixas de temperatura, dispositivo, fonte de dados; usuários (gestor) |

O painel é uma PWA: pode ser instalado no celular como aplicativo. O layout funciona em
computador e celular.

## 8. Segurança

| Camada | Medida |
|---|---|
| Dispositivo → API | HTTPS com certificado verificado; chave do dispositivo no cabeçalho |
| Pessoas → API | Login com e-mail e senha; token assinado (JWT) com validade de 8 horas |
| Senhas | Guardadas apenas como hash scrypt com sal aleatório; a senha nunca é armazenada |
| Permissões | Perfis Operador Logístico e Gestor, conferidos pela API em cada chamada |
| Login | Mesma resposta e mesmo tempo para e-mail inexistente e senha errada |
| Segredos | Fora do código: configurações da Function no Azure e `secrets.h` fora do Git |
| Navegador | CORS da API aceita somente o endereço publicado do painel e o servidor local de desenvolvimento |
| Dados | Leituras inválidas (NaN, fora da faixa física, horário impossível) são recusadas |

## 9. Publicação e testes

| Parte | Publicação automática | Publicação manual |
|---|---|---|
| API | GitHub Actions `publicar-api.yml`: a cada envio à branch `everson` que altere a API, roda os testes e publica | `bash publicar.sh` em `cloud/function/` |
| Painel | GitHub Actions `publicar-site.yml`: a cada envio à branch `everson`, confere os scripts e publica | `bash publicar.sh` no repositório do painel |
| Firmware | — | Compilado e gravado no ESP32 pelo cabo USB |

**Credencial da publicação automática.** O GitHub entra no Azure por OIDC: não existe senha
guardada no repositório. A identidade `coldtrack-github-deploy` tem permissão apenas no grupo
de recursos `rg-coldtrack` e só é aceita para a branch `everson` destes dois repositórios.
A publicação manual usa o **Azure CLI** (comando `az`) autenticado na assinatura do projeto.

Testes:

| Tipo | Onde roda | O que cobre |
|---|---|---|
| Testes automatizados da API | Máquina local e GitHub Actions | Contrato, horário, filtros, senha, token, cadastros |
| Compilação do firmware | GitHub Actions | Sketch compilado para ESP32-C3 com DHT22 e com DHT11 |
| Simulação | Wokwi (wokwi-cli) | Firmware real enviando ao Azure; queda de conexão; excursão térmica |
| Ponta a ponta | Navegador automatizado | Login, perfis, cadastros e telas no painel publicado |

## 10. Custos

Todos os serviços operam na camada gratuita ou de consumo, cobertos pelo crédito da assinatura
acadêmica. O custo previsto fora do Azure é o hardware da versão final: módulo 4G com GPS,
chip de dados e fonte veicular.

## 11. Limitações atuais e evolução

| Hoje | Evolução prevista |
|---|---|
| Conexão por Wi-Fi | Módulo 4G com chip e GPS; envio por MQTT via Azure IoT Hub |
| Uma empresa por instalação; implantação assistida pela equipe | Cadastro de empresas, com dados separados por cliente |
| Mesma chave para todos os dispositivos | Chave própria por dispositivo, registrada por QR code |
| Wi-Fi configurado no código | Configuração pelo celular (rede de configuração do próprio ESP32) |
| Faixas de temperatura fixas no firmware | Perfil de carga escolhido no painel e enviado ao sensor |
| Testes no ambiente publicado | Ambiente de testes separado |

## 12. Glossário

| Termo | Significado |
|---|---|
| API | Conjunto de endereços que recebem e devolvem dados; aqui, em JSON |
| JSON | Formato de texto para dados estruturados, usado entre dispositivo, API e painel |
| HTTPS / TLS | Comunicação criptografada pela internet |
| Serverless | Código executado sob demanda pelo provedor, sem servidor fixo para administrar |
| NoSQL | Banco que guarda documentos em vez de tabelas com colunas fixas |
| Container | Coleção de documentos no Cosmos DB (equivalente a uma tabela) |
| Chave de partição | Campo que define como os documentos são distribuídos no banco |
| JWT | Token de acesso assinado, entregue após o login |
| Hash de senha | Transformação irreversível da senha; permite conferir sem guardá-la |
| CORS | Regra do navegador que define quais sites podem chamar a API |
| PWA | Site que pode ser instalado como aplicativo no celular |
| Store-and-forward | Guardar dados sem conexão e enviar quando a conexão volta |
| CI (GitHub Actions) | Testes executados automaticamente a cada envio ao repositório |

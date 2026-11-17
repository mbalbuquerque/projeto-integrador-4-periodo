# Política de privacidade e exclusão de dados do ColdTrack

Esta política explica quais dados pessoais o ColdTrack trata, para quê, por quanto tempo, com
quem são compartilhados e como o titular exerce seus direitos, conforme a Lei nº 13.709/2018
(LGPD). Ela complementa o levantamento técnico em [`lgpd.md`](lgpd.md), que é a fonte dos dados
listados aqui. O ColdTrack é um protótipo acadêmico; os pontos abaixo descrevem o que o sistema
faz hoje e a proposta da equipe para um uso real, sem substituir revisão jurídica.

## Controlador e contato

- **Controlador:** a equipe do projeto acadêmico ColdTrack (Projeto Integrador, Faculdade
  Senac PE, 4º período, 2026.2), responsável pelas decisões sobre o tratamento.
- **Encarregado (DPO):** não designado. Para um uso real, a empresa que operar o sistema deve
  indicar um.
- **Canal de contato:** uma *issue* no repositório
  <https://github.com/mbalbuquerque/projeto-integrador-4-periodo/issues>, com o rótulo
  `documentation` ou `question`. As issues são públicas: **não escrever senha, token, CPF nem
  outro dado pessoal na issue**. Informar apenas que é uma solicitação de titular e o tipo de
  pedido; a equipe responde combinando um meio privado para conferir a identidade.

## Dados tratados

| dado | de quem | finalidade | base legal (proposta) |
|---|---|---|---|
| Nome, e-mail e perfil (operador, gestor ou motorista) e, do motorista, o código do veículo vinculado | usuário da empresa | acesso ao painel e controle de permissão | execução de contrato (art. 7º, V) |
| Hash da senha (scrypt, com sal); a senha em si não é guardada | usuário | autenticação | execução de contrato (art. 7º, V) |
| Empresa vinculada ao usuário | usuário | separar os dados de cada empresa | execução de contrato (art. 7º, V) |
| Nome da empresa e data de criação | empresa | identificar o cliente | execução de contrato (art. 7º, V) |
| Temperatura, umidade, sinal Wi-Fi e identificador do sensor, vinculados a veículo e viagem | empresa (não é dado pessoal por si) | monitorar a carga | execução de contrato (art. 7º, V) |
| Origem, destino e carga de cada viagem; tipo e identificação dos veículos | empresa | acompanhar a operação | execução de contrato (art. 7º, V) |
| Endereço IP | usuário e visitante | limitar tentativas de login e de uso, por segurança | legítimo interesse (art. 7º, IX) |
| Perguntas ao chat do site e ao assistente do painel | visitante e usuário | responder na hora; só a contagem de uso é guardada | execução de contrato (art. 7º, V) e legítimo interesse (art. 7º, IX) |

Não são coletados localização do motorista, CPF, telefone nem dados pessoais sensíveis pela API.
O endereço IP não é gravado em texto: o contador de limite usa um hash e expira sozinho.

## Retenção

| dado | quanto tempo |
|---|---|
| Cadastros (usuários, empresa, veículos, sensores, viagens) | até o gestor removê-los, ou até a exclusão da empresa (ver abaixo) |
| Leituras dos sensores | sem prazo definido hoje: o container não tem expiração e as leituras só saem com a exclusão da empresa |
| Contadores de limite (IP hasheado) | expiram sozinhos, em até 2 dias |
| Logs do Application Insights (sem senha, token nem texto das perguntas; e-mail mascarado) | 90 dias |
| Perguntas ao chat e ao assistente | não são gravadas |

## Compartilhamento e operadores

Os dados não são vendidos nem cedidos a terceiros. Para funcionar, o sistema usa a plataforma
Microsoft Azure, que atua como **operador** (art. 5º, VII) e trata os dados em nome do
controlador:

- **Azure Cosmos DB, Azure Functions, Azure Storage e Application Insights:** cadastros,
  leituras, hospedagem da API e do painel e logs, na região Brazil South.
- **Azure OpenAI:** recebe o texto da pergunta e, no assistente do painel, um resumo dos
  veículos, viagens e leituras da própria empresa, para gerar a resposta. O texto não é
  gravado pelo ColdTrack. Os deploys são do tipo *GlobalStandard*, em que o processamento pode
  ocorrer fora do Brasil; para uso real, avaliar a transferência internacional (art. 33).
- **ThingSpeak:** recebimento opcional de temperatura, umidade e sinal do sensor, usado como
  experimento e na tela de demonstração. Não contém dado pessoal.

## Direitos do titular (art. 18)

| direito | como é atendido hoje |
|---|---|
| Confirmação de que há tratamento e acesso aos dados | o próprio usuário vê nome, e-mail, perfil e empresa no painel (`GET /eu`); o gestor lista os usuários da empresa. Não há rota de exportação: pedidos de cópia completa são atendidos pela equipe, por consulta manual ao banco |
| Correção de dados incompletos ou desatualizados | o gestor corrige o cadastro de usuário (`PUT /usuarios/{id}`) e o próprio usuário troca a senha (`POST /senha`) |
| Anonimização, bloqueio ou eliminação de dados desnecessários ou tratados em desconformidade | exclusão de usuário pelo gestor (`DELETE /usuarios/{id}`) e da empresa inteira pelo gestor (`DELETE /empresa`); demais casos, por pedido à equipe |
| Portabilidade | não há exportação automática; atendida sob pedido, por extração manual em formato JSON |
| Eliminação dos dados tratados com consentimento | o sistema não usa consentimento como base; vale o procedimento de exclusão abaixo |
| Informação sobre com quem os dados são compartilhados | esta política (seção anterior) |
| Informação sobre a possibilidade de não consentir e suas consequências | sem cadastro não há acesso ao painel; o chat do site pode ser usado sem cadastro |
| Revogação do consentimento | não se aplica, pelo mesmo motivo |
| Oposição a tratamento baseado em legítimo interesse | pedido à equipe pelo canal acima; os contadores de IP expiram sozinhos em até 2 dias |

O prazo proposto para responder é de 15 dias corridos a partir da confirmação de identidade.

## Como pedir a exclusão

### Exclusão de um usuário

O gestor da empresa remove o usuário no painel (Configurações) ou por `DELETE /usuarios/{e-mail}`. A
remoção é imediata e o token do usuário deixa de valer na chamada seguinte, porque a API relê
o usuário no banco a cada requisição. O gestor não consegue remover o próprio usuário.
Usuário sem gestor que o represente (por exemplo, o único gestor da empresa) segue o
procedimento manual abaixo.

### Exclusão da empresa inteira

O gestor da empresa exclui a empresa e todos os dados dela pela API, com `DELETE /empresa`
(detalhe em [`api.md`](api.md#delete-empresa)). O pedido leva:

- `confirmacao`: o nome da empresa como foi cadastrado (ou o código dela, `E-XXXXXXXX`, que
  aparece em `GET /eu`), digitado pelo gestor;
- `senha`: a senha atual do gestor. A senha errada conta na mesma espera do login.

Só gestor pede, e só a empresa dele (a empresa vem do token, nunca do corpo). A API apaga, nesta
ordem: as sessões e as inscrições de push dos outros usuários, os sensores (a chave deixa de
valer), todas as leituras da empresa, as viagens, os veículos, os outros usuários, a empresa e,
por último, o gestor que pediu. Ao final, todos os tokens da empresa respondem `401` e o login
de qualquer usuário dela falha.

Se o pedido parar no meio (erro do banco, ou empresa com muitas leituras que passa do tempo de
120 s por pedido e recebe `202`), o gestor repete o mesmo pedido, que continua de onde parou; o
que já foi apagado continua apagado. Enquanto a empresa existe, a confirmação aceita o nome;
depois, só o código. O log registra só o código da empresa e as contagens, sem e-mail nem nome.

Dados que permanecem e saem sozinhos: os logs do Application Insights (até 90 dias, com e-mail
mascarado) e os contadores de limite (hash, até 2 dias). Não há como apagar um item isolado
desses logs; a política de retenção é o mecanismo de eliminação.

O painel ainda não tem o botão de exclusão em Configurações; até ele existir, o gestor chama a
rota pela documentação interativa (`/api/docs`, botão **Authorize** com o token) ou pede à
equipe pelo canal acima. Empresa sem gestor que a represente (por exemplo, o único gestor
removido por fora) segue o procedimento manual: a equipe, no *Data Explorer* do Cosmos DB
`cosmos-coldtrack-7319` (banco `coldtrack`), executa em cada container
`SELECT * FROM c WHERE c.empresaId = "E-XXXXXXXX"` e exclui os itens na mesma ordem da rota,
apagando por último o item de `empresas` com `id` igual ao código.

### Limitações registradas

- Não existe rota de exportação dos dados; a cópia completa e a portabilidade dependem de
  procedimento manual da equipe, sem prazo garantido por sistema.
- A exclusão da empresa existe na API, mas ainda não tem botão no painel.
- Leituras de sensores não têm prazo de retenção; só saem com a exclusão da empresa.
- Não há confirmação de e-mail no cadastro, então a identidade do solicitante é conferida
  pela equipe, fora do sistema.
- Backups periódicos do Cosmos DB podem conter os dados excluídos até o fim do ciclo de
  retenção do backup.

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
| Nome, e-mail e perfil (operador ou gestor) | usuário da empresa | acesso ao painel e controle de permissão | execução de contrato (art. 7º, V) |
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
| Cadastros (usuários, empresa, veículos, sensores, viagens) | até a empresa ou o gestor removê-los, ou até a exclusão da empresa (ver abaixo) |
| Leituras dos sensores | sem prazo definido hoje: o container não tem expiração e as leituras só saem por exclusão manual |
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
| Anonimização, bloqueio ou eliminação de dados desnecessários ou tratados em desconformidade | exclusão de usuário pelo gestor (`DELETE /usuarios/{id}`); demais casos, por pedido à equipe |
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

**A API não tem rota para excluir uma empresa.** `POST /empresas` cria, mas não existe
`DELETE /empresas`; as rotas de exclusão (`DELETE /usuarios`, `/dispositivos`, `/veiculos`,
`/viagens`) removem um item por vez e não apagam as leituras dos sensores. Isso está registrado
como limitação em [`seguranca.md`](seguranca.md) e nos pontos em aberto de [`lgpd.md`](lgpd.md).

Procedimento manual, executado pela equipe (quem tem acesso ao Cosmos DB `cosmos-coldtrack-7319`,
banco `coldtrack`, pelo portal do Azure, em *Data Explorer*):

1. Abrir uma issue pedindo a exclusão, sem dados pessoais, e confirmar a identidade de um
   gestor da empresa por um meio privado. Só gestor da empresa pode pedir a exclusão dela.
2. Anotar o código da empresa (`E-XXXXXXXX`), que aparece no cadastro do gestor.
3. Em cada container abaixo, executar `SELECT * FROM c WHERE c.empresaId = "E-XXXXXXXX"` e
   excluir os itens retornados, nesta ordem:

   | ordem | container | o que remove |
   |---|---|---|
   | 1 | `usuarios` | todos os usuários da empresa (corta o acesso e invalida os tokens) |
   | 2 | `leituras` | leituras dos sensores da empresa |
   | 3 | `viagens` | viagens |
   | 4 | `veiculos` | veículos |
   | 5 | `dispositivos` | sensores e hashes de chave |
   | 6 | `empresas` | o item com `id` igual ao código da empresa |

4. Conferir com a mesma consulta que nenhum container retorna itens, e responder na issue que a
   exclusão foi feita, sem repetir dados pessoais.
5. Dados que permanecem e saem sozinhos: os logs do Application Insights (até 90 dias, com
   e-mail mascarado) e os contadores de limite (até 2 dias). Não há como apagar um item
   isolado desses logs; a política de retenção é o mecanismo de eliminação.

### Limitações registradas

- Não existe rota de exclusão de empresa nem de exportação dos dados; os dois pedidos dependem
  de procedimento manual da equipe, sem prazo garantido por sistema.
- A exclusão manual não é automatizada nem testada; deve ser conferida a cada execução.
- Leituras de sensores não têm prazo de retenção; só saem por exclusão manual.
- Não há confirmação de e-mail no cadastro, então a identidade do solicitante é conferida
  pela equipe, fora do sistema.
- Backups periódicos do Cosmos DB podem conter os dados excluídos até o fim do ciclo de
  retenção do backup.

# Segurança do ColdTrack

O que protege a API, o painel e a infraestrutura hoje, o que foi corrigido depois da
revisão de segurança e o que ficou de fora de propósito, por ser um protótipo acadêmico.
Detalhe das rotas no [Swagger](https://func-coldtrack-7319.azurewebsites.net/api/docs) e em [`api.md`](api.md); da infraestrutura em
[`../infra/README.md`](../infra/README.md).

## Controles em vigor

### Separação entre empresas

- O token leva a empresa, e toda consulta filtra por ela. Veículos e viagens são gravados com
  id `<empresa>~<código>`: duas empresas podem usar o mesmo código sem enxergar uma a outra.
- Item de outra empresa responde igual a item inexistente (`404`).
- O assistente do painel recebe só consultas já presas à empresa do token; ele não tem como
  pedir dados de outra.

### Acesso e perfis

- A cada chamada a API relê o usuário no banco. O perfil que vale é o atual, não o do token;
  usuário removido, senha trocada, `POST /sair` ou empresa diferente derrubam o token na hora.
  Cadastro sem perfil ou sem empresa é negado (`403`), nunca liberado.
- Campos que o cliente não deveria definir (empresa, perfil de quem cria a empresa, hash da
  senha, versão da sessão) são ignorados: a API monta o documento só com os campos
  previstos e põe a empresa do token.

### Senhas, tokens e chaves

- Senha com scrypt (N = 2^14, r = 8, p = 1) e sal aleatório por usuário; comparação em
  tempo constante.
- Token JWT HS256 de 8 horas, com segredo de 64 caracteres (app setting `JWT_SECRET`) e a
  versão da sessão do usuário. Só HS256 é aceito (`alg: none` é recusado).
- Chave de cada sensor: 32 bytes aleatórios, mostrada uma vez; o banco guarda só o SHA-256.
  A chave só vale para o próprio `deviceId`.

### Entrada e saída

- Consultas ao Cosmos sempre parametrizadas (`@e`, `@device`...), nunca com texto do
  usuário concatenado.
- O painel é em React, que escapa o texto ao mostrar; a exportação CSV escapa as células,
  para um texto cadastrado não virar fórmula ao abrir na planilha.
- Logs sem senha, sem token e sem o texto das perguntas; e-mails aparecem mascarados
  (`a***@dominio.com`).

### Transporte e nuvem

- Function App só aceita HTTPS (`httpsOnly`); TLS mínimo 1.2 na Function, nos Storages e no
  Cosmos. CORS liberado só para o painel publicado.
- Publicação pelo GitHub Actions com OIDC: sem senha guardada no repositório, e só a branch
  `everson` consegue publicar.
- Azure OpenAI acessado pela identidade gerenciada da Function, com as chaves de API
  desligadas no recurso.
- Nenhum segredo no histórico do Git (conferido na revisão).

## Correções feitas depois da revisão

| problema | correção |
|---|---|
| Qualquer pessoa podia manter uma conta bloqueada repetindo senhas erradas, e o `429` do bloqueio só aparecia para contas reais (revelava quem tem conta). | Mesma resposta `401` para e-mail inexistente, senha errada e conta em espera. No lugar do bloqueio fixo, espera que começa em 1 min na 5ª falha e dobra até 15 min; tentativas durante a espera não a estendem. Limite de 20 falhas por IP a cada 15 min, em qualquer conta. |
| O IP do limite vinha do primeiro item do `X-Forwarded-For`, que o cliente escreve. | IP do `X-Azure-ClientIP` ou do último item do `X-Forwarded-For` (o que o Azure acrescenta). |
| O login regravava o cadastro inteiro ao contar a falha: podia desfazer uma troca de senha feita ao mesmo tempo, e duas falhas simultâneas contavam uma. | Falhas, espera, troca e redefinição de senha gravadas com `patch_item` (só os campos certos, soma atômica no banco). |
| Limites do `/chat`, do `/assistente` e do login contados na memória de cada instância. | Contadores no container `limites` do Cosmos, somando todas as instâncias. Cotas diárias novas: 2000 perguntas no chat do site e 300 por empresa no assistente. |
| Gestor redefinia a própria senha em `PUT /usuarios/<próprio e-mail>` sem saber a atual (um token roubado bastava para tomar a conta). | Recusado com `400`; a própria senha só muda em `POST /senha`, com a atual. |
| Texto gravado num cadastro (nome de veículo, carga) podia instruir o assistente do painel a mandar o usuário para um site falso. | O bloco de dados vai marcado como não confiável e o prompt proíbe seguir instruções dele, escrever links e pedir login ou credencial. Toda resposta do `/chat` e do `/assistente` troca links que não são do site por `[link removido]`. |
| Sair do painel só apagava o token do navegador; o token continuava valendo até vencer. | `POST /sair` sobe a versão da sessão e derruba todos os tokens do usuário. |
| E-mails completos nos logs. | E-mails mascarados. |
| Usuário sem `perfil` no banco derrubava a rota com erro 500. | Negado com `403`. |

## Limitações conhecidas (aceitas no protótipo)

- **Descobrir se um e-mail tem conta pelo cadastro.** `POST /empresas` e `POST /usuarios`
  respondem `409` quando o e-mail já existe, inclusive em outra empresa. Fechar isso exige
  confirmação de e-mail (mandar um link e só criar a conta depois), que o protótipo não tem.
- **Ids de sensor são globais.** Dois clientes não podem registrar o mesmo `deviceId`, e o
  `409` revela que o id está em uso em alguma empresa.
- **Segredos em app settings.** A connection string do Cosmos e o `JWT_SECRET` ficam nas app
  settings da Function, e não em Key Vault com identidade gerenciada. Quem tem acesso de
  leitura às configurações da Function App vê os dois.
- **Token no `localStorage`.** O painel guarda o token no navegador; um XSS no painel poderia
  lê-lo. A proteção é o React escapar o texto e uma CSP por `<meta>`: o site estático do
  Storage não permite cabeçalhos HTTP próprios (CSP por cabeçalho, HSTS).
- **Telemetria sem autenticação antes da leitura no banco.** `POST /telemetria` lê o
  dispositivo no Cosmos antes de conferir a chave; quem chama em massa com ids aleatórios
  gasta leituras do banco (custo), sem gravar nada.
- **Espera da conta ainda pode ser provocada.** Um atacante com muitos IPs consegue manter
  uma conta em espera (no máximo 15 min por vez). O gestor tira a conta da espera ao
  redefinir a senha.
- **Janelas fixas.** Os limites contam por minuto, 15 min ou dia corrente (UTC); na virada
  da janela passam até o dobro de chamadas em sequência.

# LGPD no ColdTrack

Levantamento dos dados pessoais tratados pelo sistema, com base no que o código e a infraestrutura
fazem hoje (Lei nº 13.709/2018). É um protótipo acadêmico; as bases legais abaixo são a proposta da
equipe para um uso real e não substituem revisão jurídica.

## Dados tratados

| Dado | Titular | Onde fica | Finalidade |
|---|---|---|---|
| Nome, e-mail e perfil (operador, gestor) | Usuário da empresa | Cosmos DB, container de usuários | Acesso ao painel e controle de permissão |
| Hash da senha (scrypt, com sal) | Usuário | Cosmos DB | Autenticação; a senha em si nunca é guardada |
| Empresa vinculada ao usuário | Usuário | Cosmos DB | Separar os dados de cada empresa |
| Temperatura, umidade, RSSI e identificador do sensor | Não é dado pessoal por si; associado a veículo e viagem da empresa | Cosmos DB | Monitorar a carga |
| Origem, destino e carga de cada viagem | Empresa | Cosmos DB | Acompanhar a operação |
| Endereço IP | Usuário e visitante | Contadores de limite no Cosmos (expiram sozinhos) | Limitar tentativas de login e de uso |
| Inscrição de alerta push (endereço do serviço de push e chaves do navegador) | Usuário | Cosmos DB, no cadastro do usuário | Mandar alerta de temperatura ao aparelho; sai com `DELETE /push/inscricao`, `POST /sair` ou quando o serviço de push diz que expirou |
| Perguntas ao chat e ao assistente | Usuário e visitante | Não são gravadas | Respondidas na hora; só contagem de uso |

Não há coleta de localização do motorista, CPF, telefone ou dados sensíveis na API. O painel tem
uma máscara de CPF no cadastro, mas a API não grava esse campo.

## Princípios aplicados

- **Necessidade:** só nome, e-mail e perfil são guardados do usuário.
- **Segurança:** HTTPS com TLS 1.2 no mínimo, senha com scrypt, token com sessão revogável e
  separação por empresa (ver `seguranca.md` e `stride.md`).
- **Minimização nos registros:** logs sem senha, token nem texto das perguntas; e-mail mascarado
  (`a***@dominio.com`).
- **Retenção:** logs do Application Insights por 90 dias; contadores de limite expiram sozinhos
  (TTL do Cosmos); cadastros ficam até a empresa ou o gestor removê-los.
- **Direitos do titular:** o gestor consegue corrigir (`PUT /usuarios/{id}`) e excluir
  (`DELETE /usuarios/{id}`) o cadastro de um usuário da empresa; a troca de senha é feita pelo
  próprio usuário (`POST /senha`). O gestor também exclui a empresa inteira (`DELETE /empresa`),
  com o nome da empresa digitado e a senha atual: saem usuários (com as inscrições de push),
  sensores, leituras, veículos, viagens e a empresa, e todos os tokens dela param de valer (ver
  [`api.md`](api.md#delete-empresa)).

## Base legal proposta

Execução de contrato entre a empresa cliente e o serviço, para o cadastro e o acesso dos usuários;
legítimo interesse para os registros de segurança (limite de tentativas e logs).

## Pontos em aberto

- Termo de uso e publicação da política de privacidade no site (a política está em
  [`politica-de-privacidade.md`](politica-de-privacidade.md)).
- Botão de exclusão da empresa no painel (a rota `DELETE /empresa` existe; a tela ainda não a
  chama).
- Rota de exportação dos dados (portabilidade e cópia completa), hoje atendida manualmente.
- Confirmação de e-mail no cadastro, que evita cadastrar o e-mail de outra pessoa.
- Definir quem é o encarregado (DPO) caso o sistema vá para uso real.

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
  próprio usuário (`POST /senha`).

## Base legal proposta

Execução de contrato entre a empresa cliente e o serviço, para o cadastro e o acesso dos usuários;
legítimo interesse para os registros de segurança (limite de tentativas e logs).

## Pontos em aberto

- Política de privacidade e termo de uso no site.
- Fluxo de exclusão da empresa inteira (hoje só é possível por usuário).
- Confirmação de e-mail no cadastro, que evita cadastrar o e-mail de outra pessoa.
- Definir quem é o encarregado (DPO) caso o sistema vá para uso real.

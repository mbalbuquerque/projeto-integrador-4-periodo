# Roteiro da pesquisa com usuários reais

Instrumento para a coleta com pessoas reais, atendendo ao critério de roteiro da issue #38.
Meta da prévia: ≥ 5 entrevistas ou ≥ 20 respostas. As respostas são registradas em
[`respostas-pesquisa-real.md`](respostas-pesquisa-real.md). Este arquivo não contém resultado.

## Objetivo

Testar com usuários reais as hipóteses levantadas na pesquisa secundária e nas entrevistas
simuladas ([`pesquisa-secundaria.md`](pesquisa-secundaria.md),
[`entrevistas-simuladas.md`](entrevistas-simuladas.md),
[`persona-jornada-proposta.md`](persona-jornada-proposta.md)), em especial os pontos marcados
como "sem fonte". Os resultados confirmam, corrigem ou descartam a persona, a jornada e a
proposta de valor provisórias.

## Hipóteses testadas

| id | hipótese | origem |
|---|---|---|
| H1 | A temperatura da carga é acompanhada por termógrafo ou por nada; poucas operações têm acompanhamento contínuo. | E1, E2; F6, F10 |
| H2 | O desvio de temperatura costuma ser percebido só na entrega, e já houve perda ou problema de carga por isso. | E1, E4; F2, F10 |
| H3 | Ao receber um alerta, a ação é checar porta e equipamento e avisar motorista e gestor; o fluxo real não está documentado. | E1, E5 |
| H4 | O motorista precisa de aviso curto e imediato (luz e mensagem) e teme que o registro seja usado contra ele. | E2; F12 |
| H5 | O gestor usa computador no escritório e celular em campo; excesso de alerta leva a ignorá-los. | E1, E5 |
| H6 | A decisão de compra é da transportadora e o custo de uma carga rejeitada é o termo de comparação. | E1, E2, E4 |
| H7 | Dado não auditável gera desconfiança; o histórico por viagem serve de prova para cliente e seguradora. | E1, E4; F10, F11 |

## Quem perguntar

Meta: 3 a 5 pessoas por entrevista ou conversa, ou 20 respostas se for por formulário.

| perfil | quem | perguntas |
|---|---|---|
| Gestor | gestor ou operador de frota e logística; responsável de logística de produtor ou exportador; profissional de distribuição de alimentos ou medicamentos refrigerados | G1 a G8 e C1 |
| Motorista | motorista de caminhão refrigerado (baú frigorífico) | M1 a M6 e C1 |

Quem trabalha com distribuição de alimentos ou medicamentos responde como gestor ou como
motorista, conforme a função, e o perfil fica anotado no registro.

## Aviso e consentimento (LGPD)

Texto a ler ou colar antes das perguntas:

> Esta pesquisa faz parte de um trabalho acadêmico sobre monitoramento de temperatura em
> caminhões refrigerados. A participação é voluntária e anônima: não pedimos nome, telefone,
> empresa nem placa, e nenhum dado que identifique você é guardado. As respostas são usadas
> apenas no trabalho. Você pode parar a qualquer momento. Ao responder, você concorda em
> participar.

Regra de registro: o respondente recebe apenas um código (R1, R2, ...). O número de telefone
usado no envio por WhatsApp não é copiado para o registro.

## Parte 1 — perguntas

Tipos: **F** = fechada, **A** = aberta. As opções ficam entre colchetes; escolha única, salvo
indicação.

### Perfil gestor (9 itens)

| n | pergunta | tipo | testa |
|---|---|---|---|
| G1 | Qual é a sua função e que tipo de carga refrigerada você acompanha? | A | perfil |
| G2 | Como você acompanha a temperatura da carga durante a viagem hoje? [não acompanho · termômetro manual · registrador (data logger) ou termógrafo · sistema com rastreamento em tempo real · outro] | F | H1 |
| G3 | Já teve perda ou problema com carga por temperatura? [nunca · uma vez · mais de uma vez] | F | H2 |
| G4 | Quando a temperatura sai da faixa, em quanto tempo alguém fica sabendo? [na hora · algumas horas · só na entrega · não sei] | F | H2 |
| G5 | Ao descobrir um desvio, o que você faz primeiro e quem é avisado? | A | H3 |
| G6 | Onde você preferiria ver o alerta? (pode marcar mais de uma) [notificação no celular · mensagem no WhatsApp · computador · outro] | F | H5 |
| G7 | Se o sistema enviasse alertas demais, você [ignoraria · leria, mas incomoda · não incomoda] | F | H5 |
| G8 | Quanto você pagaria por mês, por veículo, para evitar essa perda? [nada · até R$ 50 · R$ 50 a R$ 150 · acima de R$ 150 · não sei] Quem decide a compra na sua empresa? | F + A | H6 |
| C1 | O que faria você desconfiar ou não usar um sistema assim? (pode marcar mais de uma) [dado que não posso conferir · sensor que falha sem avisar · trabalho extra · preço · outro] | F | H7 |

### Perfil motorista (7 itens)

| n | pergunta | tipo | testa |
|---|---|---|---|
| M1 | Como você sabe se a temperatura do baú está certa? [não sei · olho o painel do equipamento · alguém me avisa · outro] | F | H1 |
| M2 | Já aconteceu de a carga estragar por temperatura? [nunca · uma vez · mais de uma vez] Se sim, o que você fez? | F + A | H2, H3 |
| M3 | Qual aviso você aceitaria durante a viagem? (pode marcar mais de um) [luz no baú · aviso no celular · ligação do gestor · nenhum] | F | H4 |
| M4 | Se o aparelho guardasse o histórico da viagem, isso seria [bom, protege o motorista · indiferente · ruim, pode ser usado contra mim] | F | H4, H7 |
| M5 | Em movimento, quanto tempo você aceita olhar uma mensagem no celular? [nenhum · poucos segundos · só parado] | F | H4 |
| M6 | Quem na empresa decide comprar um equipamento assim? [dono · gestor · eu mesmo · não sei] | F | H6 |
| C1 | O que faria você desconfiar ou não usar um sistema assim? (pode marcar mais de uma) [dado que não posso conferir · sensor que falha sem avisar · trabalho extra · preço · outro] | F | H7 |

## Parte 2 — validação (final)

Aplicar na entrega final, com o PWA publicado e uma pessoa por vez. Link do PWA:
<https://stcoldtrackweb7319.z15.web.core.windows.net>. O avaliador observa e anota, sem ajudar.

### Tarefas

| n | tarefa | sucesso | anotar |
|---|---|---|---|
| T1 | Descobrir se algum veículo está em situação crítica agora. | achou o veículo e o status | tempo (s) · acertou sim/não |
| T2 | Abrir o histórico de uma viagem e dizer a maior temperatura registrada. | leu o valor correto | tempo (s) · acertou sim/não |
| T3 | Encontrar a última ocorrência de alerta e dizer quanto tempo durou. | leu início e duração | tempo (s) · acertou sim/não |
| T4 | Gerar o relatório de um período e dizer o percentual fora da faixa. | achou o valor | tempo (s) · acertou sim/não |

As tarefas são do perfil gestor. Com motorista, aplicar só a tela de alerta do motorista, se
estiver disponível na entrega, com a tarefa "dizer o que o alerta pede para fazer".

### SUS (System Usability Scale)

Escala de 1 (discordo totalmente) a 5 (concordo totalmente).

1. Acho que gostaria de usar este sistema com frequência.
2. Achei o sistema desnecessariamente complexo.
3. Achei o sistema fácil de usar.
4. Acho que precisaria de ajuda de uma pessoa com conhecimento técnico para usar o sistema.
5. Achei que as várias funções do sistema estavam muito bem integradas.
6. Achei que o sistema apresentava muita inconsistência.
7. Imagino que as pessoas aprenderiam a usar este sistema rapidamente.
8. Achei o sistema atrapalhado de usar.
9. Senti-me confiante ao usar o sistema.
10. Precisei aprender várias coisas novas antes de conseguir usar o sistema.

Cálculo: itens ímpares contribuem com (resposta − 1); itens pares, com (5 − resposta). Somar as
dez contribuições e multiplicar por 2,5, o que dá um valor de 0 a 100. A média entre os
respondentes é o SUS do sistema.

### Intenção de uso

**U1.** Se este sistema estivesse disponível para a sua operação, qual a chance de você usá-lo?
[1 muito baixa · 2 baixa · 3 incerta · 4 alta · 5 muito alta] O que faltaria para isso?

## Versão para WhatsApp (copiar e colar)

Enviar o bloco de introdução e só o bloco do perfil da pessoa. O mesmo texto está em
`ColdTrack-pesquisa-whatsapp.txt`, fora do repositório.

```
Olá! Somos estudantes e fazemos um trabalho acadêmico sobre monitoramento de temperatura em
caminhões refrigerados. Pode responder algumas perguntas rápidas (uns 3 minutos)? É anônimo:
não precisa dizer nome nem empresa, e nenhum dado que identifique você é guardado. Se não
quiser, sem problema. Pode responder só com o número e a letra, ou com texto.
```

Perfil gestor:

```
1. Qual a sua função e que carga refrigerada você acompanha?
2. Como acompanha a temperatura durante a viagem hoje?
   a) não acompanho  b) termômetro manual  c) registrador/termógrafo
   d) sistema em tempo real  e) outro
3. Já teve perda ou problema de carga por temperatura?
   a) nunca  b) uma vez  c) mais de uma vez
4. Quando a temperatura sai da faixa, em quanto tempo alguém fica sabendo?
   a) na hora  b) algumas horas  c) só na entrega  d) não sei
5. Ao descobrir, o que você faz primeiro e quem é avisado?
6. Onde prefere ver o alerta? (pode marcar mais de um)
   a) notificação no celular  b) WhatsApp  c) computador  d) outro
7. Se viessem alertas demais, você
   a) ignoraria  b) leria, mas incomoda  c) não incomoda
8. Quanto pagaria por mês, por veículo, para evitar essa perda?
   a) nada  b) até R$ 50  c) R$ 50 a R$ 150  d) acima de R$ 150  e) não sei
   E quem decide a compra aí na empresa?
9. O que faria você desconfiar ou não usar um sistema assim? (pode marcar mais de um)
   a) dado que não posso conferir  b) sensor que falha sem avisar
   c) trabalho extra  d) preço  e) outro

Obrigado!
```

Perfil motorista:

```
1. Como você sabe se a temperatura do baú está certa?
   a) não sei  b) olho o painel do equipamento  c) alguém me avisa  d) outro
2. Já aconteceu de a carga estragar por temperatura?
   a) nunca  b) uma vez  c) mais de uma vez
   Se sim, o que você fez?
3. Qual aviso aceitaria durante a viagem? (pode marcar mais de um)
   a) luz no baú  b) aviso no celular  c) ligação do gestor  d) nenhum
4. Se o aparelho guardasse o histórico da viagem, isso seria
   a) bom, protege o motorista  b) indiferente  c) ruim, pode ser usado contra mim
5. Em movimento, quanto tempo aceita olhar uma mensagem no celular?
   a) nenhum  b) poucos segundos  c) só parado
6. Quem decide comprar um equipamento assim na empresa?
   a) dono  b) gestor  c) eu mesmo  d) não sei
7. O que faria você desconfiar ou não usar um sistema assim? (pode marcar mais de um)
   a) dado que não posso conferir  b) sensor que falha sem avisar
   c) trabalho extra  d) preço  e) outro

Obrigado!
```

## Campos para Google Forms

Texto de consentimento na descrição do formulário. Desativar a coleta de e-mail e de qualquer
identificação. A primeira pergunta separa o perfil e leva à seção correspondente ("ir para a
seção com base na resposta").

| seção | pergunta | tipo | opções | obrig. |
|---|---|---|---|---|
| 1 | Seu perfil | múltipla escolha | Gestor; Motorista | sim |
| Gestor | G1 função e carga acompanhada | resposta curta | | sim |
| Gestor | G2 acompanhamento hoje | múltipla escolha | não acompanho; termômetro manual; registrador ou termógrafo; sistema em tempo real; outro | sim |
| Gestor | G3 perda por temperatura | múltipla escolha | nunca; uma vez; mais de uma vez | sim |
| Gestor | G4 tempo até saber | múltipla escolha | na hora; algumas horas; só na entrega; não sei | sim |
| Gestor | G5 ação ao descobrir e quem é avisado | parágrafo | | não |
| Gestor | G6 onde ver o alerta | caixas de seleção | notificação no celular; WhatsApp; computador; outro | sim |
| Gestor | G7 alertas demais | múltipla escolha | ignoraria; leria, mas incomoda; não incomoda | sim |
| Gestor | G8 valor por veículo por mês | múltipla escolha | nada; até R$ 50; R$ 50 a R$ 150; acima de R$ 150; não sei | sim |
| Gestor | G8 quem decide a compra | resposta curta | | não |
| Gestor | C1 o que causaria desconfiança | caixas de seleção | dado que não posso conferir; sensor que falha sem avisar; trabalho extra; preço; outro | sim |
| Motorista | M1 como sabe a temperatura | múltipla escolha | não sei; olho o painel do equipamento; alguém me avisa; outro | sim |
| Motorista | M2 carga estragou | múltipla escolha | nunca; uma vez; mais de uma vez | sim |
| Motorista | M2 o que fez | parágrafo | | não |
| Motorista | M3 aviso aceito | caixas de seleção | luz no baú; aviso no celular; ligação do gestor; nenhum | sim |
| Motorista | M4 histórico da viagem | múltipla escolha | bom, protege o motorista; indiferente; ruim, pode ser usado contra mim | sim |
| Motorista | M5 tempo olhando a mensagem | múltipla escolha | nenhum; poucos segundos; só parado | sim |
| Motorista | M6 quem decide a compra | múltipla escolha | dono; gestor; eu mesmo; não sei | sim |
| Motorista | C1 o que causaria desconfiança | caixas de seleção | dado que não posso conferir; sensor que falha sem avisar; trabalho extra; preço; outro | sim |

Parte 2 (SUS e U1), se aplicada por formulário: 10 perguntas de escala linear de 1 a 5
(rótulos "discordo totalmente" e "concordo totalmente") com os textos do SUS acima; U1 em
escala linear de 1 a 5 mais um parágrafo opcional.

## Como registrar

Cada resposta recebida entra em [`respostas-pesquisa-real.md`](respostas-pesquisa-real.md), com
código R1, R2, ..., sem identificação. Ao chegar em ≥ 5 entrevistas ou ≥ 20 respostas, revisar
[`persona-jornada-proposta.md`](persona-jornada-proposta.md) indicando, para cada hipótese de H1
a H7, se foi confirmada, corrigida ou descartada.

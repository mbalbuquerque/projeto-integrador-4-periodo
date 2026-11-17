# Respostas da pesquisa — SIMULADAS

> # RESPOSTAS SIMULADAS, elaboradas a partir da pesquisa secundária; nenhuma pessoa real foi entrevistada.
>
> R1 a R5 são **perfis de síntese**, não indivíduos: não têm nome, empresa, telefone nem
> placa, e nada aqui foi dito por alguém. Cada resposta é uma leitura das fontes públicas de
> [`pesquisa-secundaria.md`](pesquisa-secundaria.md) (`[F#]`) organizada no formato do
> questionário de [`roteiro-pesquisa-real.md`](roteiro-pesquisa-real.md). Decisão da equipe em
> 17/11/2026: sem tempo para entrevistas, a rodada da issue #38 é simulada e assim declarada.
> **Isto não conta como pesquisa com usuários reais** e não valida nada com o mercado; as
> perguntas sem fonte seguem abertas para a coleta real
> ([`respostas-pesquisa-real.md`](respostas-pesquisa-real.md), vazio de propósito).

## Como ler

- **[F#]**: o conteúdo da resposta está na fonte citada.
- **SF (sem fonte)**: nenhuma fonte lida cobre o ponto. O perfil responde "não sei" ou a
  equipe marca a resposta como **inferência** a validar. Nada foi inventado para tapar lacuna.
- Fontes de fornecedor ([F10]) têm interesse comercial; descrevem função, não resultado.
- Perfis: **R1** gestor de transportadora de carga refrigerada, polo frutícola do semiárido;
  **R2** responsável de logística de produtor-exportador, polo frutícola; **R3** operador de
  frota com telemetria, região metropolitana; **R4** motorista de baú frigorífico, corredor
  rodoviário Vale–Pecém; **R5** motorista de baú frigorífico, corredor Vale–Salvador.
  Os corredores seguem os portos citados em [F7].

## Parte 1 — gestor (R1 a R3)

| | R1 (transportadora) | R2 (produtor-exportador) | R3 (operador de frota) |
|---|---|---|---|
| **G1** função e carga | Programa viagens de manga e uva até o porto; safra de julho a dezembro [F7], quase metade da manga sai de setembro a novembro [F13] | Logística de manga e uva para Europa e EUA; 70% das frutas das associadas vão à UE, 90% por mar [F8] | Acompanha a frota na tela e aciona motorista e gestor (papel do perfil `operador` do produto; SF sobre rotina) |
| **G2** acompanhamento | registrador/termógrafo [F6] | registrador/termógrafo em todo embarque [F6] | sistema com rastreamento em tempo real [F10] |
| **G3** perda | existe caso documentado: rejeição por corte negro acima de 10% de frutas afetadas [F1][F2]; frequência: SF, responde "não sei" | caso documentado: carga de uva rejeitada na Europa por informação desencontrada [F8]; frequência: SF | desvios comuns: porta aberta, clima, falha do equipamento [F10]; perda própria: SF |
| **G4** tempo até saber | só na entrega, sem monitoramento contínuo [F10] | só na entrega para defeito interno [F2] | na hora, com alerta contínuo; a fonte diz "minutos" sem medição [F10] |
| **G5** ação e quem é avisado | checa porta e equipamento [F10], avisa motorista e cliente; quem é avisado na prática: SF | revisa colheita, armazenamento, transporte e tempo antes do embarque [F1]; fluxo de alerta: SF | confere o veículo e avisa motorista e gestor: SF, hipótese |
| **G6** onde ver | computador e celular: SF, inferência (aviso curto, F12) | relatório por viagem para anexar [F9]; alerta no celular: SF | tela fixa no escritório e celular fora: SF |
| **G7** alertas demais | SF, "não sei" | SF, "não sei" | tenderia a ignorar: SF, hipótese |
| **G8** preço e decisão | SF; termo de comparação: carga rejeitada [F2] | SF; termo de comparação: valor da carga [F2] | não decide compra: SF |
| **C1** desconfiança | dado que não posso conferir [F10]; promessa de seguro: o registro sozinho não garante indenização [F11] | dado sem auditoria e informação desencontrada [F8][F9] | sensor que falha sem avisar e alerta em excesso: SF |

## Parte 1 — motorista (R4 e R5)

| | R4 (Vale–Pecém) | R5 (Vale–Salvador) |
|---|---|---|
| **M1** como sabe a temperatura | SF, "não sei"; a fonte só cita termógrafo [F6] | SF, "não sei" |
| **M2** carga estragou | SF; as fontes falam de fadiga e pressão de horário, não de perda [F12] | SF; idem [F12][F6] |
| **M3** aviso aceito | luz no baú e aviso curto no celular: inferência a partir de F12 (fadiga, atenção limitada) | luz no baú; ligação do gestor só parado: inferência a partir de F12 |
| **M4** histórico da viagem | SF; ponto sensível, o registro entra em disputa de responsabilidade [F2][F11], pode proteger ou prejudicar | SF; mesma leitura [F2][F11] |
| **M5** tempo olhando a mensagem | nenhum em movimento: inferência (F12) | só parado: inferência (F12) |
| **M6** quem decide a compra | SF; a decisão de compra ser da transportadora é hipótese | SF |
| **C1** desconfiança | trabalho extra: a tecnologia "não substitui o motorista" [F12] | sensor que falha sem avisar; estrada em más condições [F6] |

## Síntese por hipótese

Veredito pelo que as **fontes** sustentam, não pelo que alguém disse. Contagem sobre os
respondentes que tinham pergunta aplicável. "Apoiou" = a resposta, com fonte, sustenta a
hipótese; "contrariou" = a fonte aponta outro caminho; "SF" = sem fonte.

| hipótese | apoiou | contrariou | SF | veredito (simulado) |
|---|---|---|---|---|
| H1 termógrafo ou nada | R1, R2 (2) | R3 (1): telemetria contínua existe em frotas [F10] | R4, R5 (2) | **corrigida**: há uma terceira via, telemetria; frequência de cada uma SF |
| H2 desvio visto só na entrega | R1, R2 (2) | R3 (1): com alerta contínuo é rápido [F10] | R4, R5 (2) | **apoiada**, condicionada a não haver monitoramento contínuo |
| H3 ação e fluxo de alerta | R1 (1, em parte) | 0 | R2, R3, R4, R5 (4) | **sem fonte**: segue hipótese |
| H4 aviso curto; medo do registro | R4, R5 (2): aviso curto, inferência de F12 | 0 | R4, R5: medo do registro (2) | **apoiada em parte** (aviso curto); o medo do registro é SF |
| H5 dispositivo e excesso de alerta | 0 | 0 | R1, R2, R3 (3) | **sem fonte**: segue hipótese |
| H6 compra da transportadora; custo da rejeição | R1, R2 (2, só como termo de comparação [F2]) | 0 | R3, R4, R5 (3) | **sem fonte** quanto a quem decide; **apoiada** como comparação |
| H7 auditoria e prova | R1, R2 (2) [F8][F9][F10] | R1 (1): para seguradora o registro não basta [F11] | R3, R4, R5 (3) | **corrigida**: serve de prova ao cliente e ao exportador, não garante seguro |

Resumo: 2 hipóteses apoiadas (H2, H6 como comparação), 2 corrigidas (H1, H7), 1 apoiada em
parte (H4), 2 sem fonte (H3, H5). Nenhuma descartada. A maior parte do que pede coleta real
(preço, dispositivo, fluxo de alerta, motorista) continua sem resposta: simular não a
substitui.

## Parte 2 — validação (SIMULADA)

> **SIMULADA.** Nenhum dos cinco respondentes usou o PWA. Resultados, tempos, notas SUS e
> intenção de uso abaixo foram **construídos pela equipe** a partir do que as telas atuais
> mostram, para exercitar o procedimento da Parte 2 do roteiro. **O SUS de respondentes
> simulados não é evidência de usabilidade real.** Serve só como ensaio do cálculo e para
> apontar atritos prováveis; a medição verdadeira exige pessoas diante do PWA publicado.

### Telas consideradas (estado de 17/11/2026)

PWA com Visão geral, Veículos, Sensores, Viagens, Alertas, Relatórios, Monitoramento
ThingSpeak, Configurações e a tela do Motorista (só para o perfil motorista). As telas de
exemplo Usuários, Auditoria e Logística foram removidas; os endereços antigos levam a
Configurações, Visão geral e Viagens.

Caminho de cada tarefa e o atrito provável, lidos nas telas:

| tarefa | caminho | atrito provável |
|---|---|---|
| T1 veículo crítico | Veículos: cada veículo mostra um selo NORMAL, ATENÇÃO, CRÍTICO ou SEM SINAL | a Visão geral mostra um veículo por vez (seletor); quem começa por ela precisa trocar de veículo |
| T2 maior temperatura da viagem | Viagens: cartão da viagem, campo "Faixa registrada" (mínima a máxima) e gráfico | o rótulo diz "Faixa registrada", não "maior temperatura"; é preciso saber que o segundo valor é o máximo |
| T3 última ocorrência e duração | Alertas: cartão "Última ocorrência" (data e hora) e, na lista, "duração" de cada ocorrência | início e duração ficam em lugares diferentes; a tela é por veículo |
| T4 percentual fora da faixa | Relatórios: cartão "Fora da faixa normal" em % | baixo; basta escolher o período |
| TM motorista | tela Motorista: pílula de status e frase ("Carga fora da faixa. Pare em local seguro e confira o baú e o equipamento.") | exige tocar em "Ativar alertas" para som e vibração |

### Tarefas (gestores R1 a R3; tempo em segundos, ok = acertou)

| respondente | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| R1 | 25 s, ok | 70 s, ok (hesitou no rótulo "Faixa registrada") | 80 s, ok (trocou de veículo no seletor) | 30 s, ok |
| R2 | 20 s, ok | 85 s, **erro** (leu a temperatura atual da Visão geral, não a da viagem) | 60 s, ok | 40 s, ok |
| R3 | 15 s, ok | 55 s, ok | 35 s, ok | 25 s, ok |
| acertos | 3/3 | 2/3 | 3/3 | 3/3 |

Total simulado: 11 de 12 tarefas (92%). T2 concentra o atrito, coerente com o rótulo da tela.

Motoristas (R4, R5), tarefa TM, conforme o roteiro (só a tela de alerta): R4 12 s, ok; R5
15 s, ok (disse que preferiria o aviso no baú, não no celular). As tarefas T1 a T4 são do
perfil gestor e não foram aplicadas a eles.

### SUS

Itens ímpares contribuem com (resposta − 1); pares, com (5 − resposta); soma × 2,5.

| resp. | respostas 1 a 10 | contribuições 1 a 10 | soma | × 2,5 |
|---|---|---|---|---|
| R1 | 4 2 4 2 4 3 4 2 3 2 | 3 3 3 3 3 2 3 3 2 3 | 28 | **70,0** |
| R2 | 4 1 5 2 4 2 5 1 4 2 | 3 4 4 3 3 3 4 4 3 3 | 34 | **85,0** |
| R3 | 5 2 4 1 4 2 5 2 4 1 | 4 3 3 4 3 3 4 3 3 4 | 34 | **85,0** |
| R4 | 3 2 4 3 3 2 4 2 3 3 | 2 3 3 2 2 3 3 3 2 2 | 25 | **62,5** |
| R5 | 3 3 4 2 3 2 4 2 3 2 | 2 2 3 3 2 3 3 3 2 3 | 26 | **65,0** |

Conferência de R1: ímpares (4−1)+(4−1)+(4−1)+(4−1)+(3−1) = 3+3+3+3+2 = 14; pares
(5−2)+(5−2)+(5−3)+(5−2)+(5−2) = 3+3+2+3+3 = 14; 14+14 = 28; 28 × 2,5 = 70,0.

**Média simulada: (70,0 + 85,0 + 85,0 + 62,5 + 65,0) / 5 = 367,5 / 5 = 73,5.** Gestores
(R1 a R3): 240 / 3 = 80,0. Motoristas (R4, R5): 127,5 / 2 = 63,75. Em escalas usuais o valor
de 68 é o ponto de referência de uso aceitável; 73,5 estaria acima, mas **o número não prova
nada**, porque nenhuma pessoa usou o sistema. O que se aproveita é a direção: a tela do
motorista, a mais curta, teve as menores notas simuladas, o que reforça levá-la à coleta real
com motorista de verdade.

### Intenção de uso (U1, escala 1 a 5)

| resp. | U1 | o que faltaria (simulado) |
|---|---|---|
| R1 | 4 | prova de que o histórico serve ao cliente; preço |
| R2 | 4 | relatório por viagem para anexar à documentação [F9] |
| R3 | 5 | alerta fora do painel (mensagem), para não depender de olhar a tela |
| R4 | 3 | que o aviso não exija olhar o celular em movimento; garantia de que o registro não vira prova contra ele |
| R5 | 3 | luz no baú, não só tela |

Média 3,8. Mesma ressalva: intenção simulada não mede interesse de mercado.

## Limitações

- Nenhuma pessoa real participou; a meta da prévia (≥ 5 entrevistas ou ≥ 20 respostas de
  usuários reais) **não foi atendida** por esta rodada, e sim substituída por decisão da equipe.
- As respostas estão presas ao que as fontes dizem; por isso metade das perguntas ficou SF.
- Tempos, erros, notas SUS e U1 da Parte 2 são construídos, não medidos.

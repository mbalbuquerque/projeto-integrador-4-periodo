# Persona, jornada e proposta de valor — proposta

> **Proposta provisória, construída sobre pesquisa secundária e entrevistas simuladas.** Não há
> fala de usuário real aqui. As fontes são as de
> [`pesquisa-secundaria.md`](pesquisa-secundaria.md) (`[F#]`); as entrevistas, as de
> [`entrevistas-simuladas.md`](entrevistas-simuladas.md) (`E1` a `E5`, todas **simuladas**).
> Afirmações marcadas *hipótese* não têm fonte e entram na lista de validação do final.

## Persona principal — Gestor de logística da transportadora

Perfil de síntese, não pessoa. Base: E1, E5 e as fontes citadas.

| | |
|---|---|
| **Papel** | Responde pela programação das viagens refrigeradas de manga e uva do Vale do São Francisco até o porto e pelo cumprimento de prazo e temperatura (E1) |
| **Contexto** | Safra concentrada: janela de julho a dezembro [F7]; quase metade da manga exportada sai entre setembro e novembro [F13]. O porto de embarque é decidido pelo armador [F7] |
| **Cobrança que recebe** | Exportador e importador pedem prova de origem e de condições em cada etapa [F9]; carga com defeito de temperatura pode ser rejeitada no destino (corte negro, acima de 10% das frutas inspecionadas) [F2] |
| **Dores** | Desvio só percebido no destino sem monitoramento contínuo [F10]; defeito invisível por fora [F1][F2]; discussão de responsabilidade sem registro [F10]; seguro de transporte que costuma excluir variação de temperatura [F11]; porta aberta, clima e falha de equipamento como causas comuns [F10] |
| **Objetivos** | Saber na hora quando uma carga sai da faixa; ter o histórico da viagem para mostrar ao cliente; reduzir rejeição |
| **O que usa hoje** | Termógrafo em caminhões e contêineres em operações de produtor-exportador [F6]; telemetria de fornecedor em frotas [F10]. Uso na transportadora do Vale: *hipótese* |
| **O que o faria desconfiar** | Dado não auditável [F10]; promessa de seguro que a apólice não cobre [F11]; alerta demais (*hipótese*) |
| **Telas** | Computador no escritório, celular em campo (*hipótese*) |

### Persona secundária — Motorista de baú refrigerado

Base: E2 e F12.

| | |
|---|---|
| **Rotina** | Viagens longas, jornadas extensas, pressão de horário, pouco descanso, falta de pontos de parada adequados [F12] |
| **Dores** | Fadiga e atenção limitada [F12]; estrada em más condições [F6]; o registro de temperatura pode ser usado a favor ou contra ele (*hipótese*, E2) |
| **Necessidade** | Aviso curto e imediato, sem exigir atenção prolongada ao celular: por isso o semáforo no próprio sensor (verde, amarelo, vermelho). Decisão de projeto fundada em F12, a validar |
| **Limite** | O equipamento não substitui o motorista [F12]; não é ele quem decide a compra (*hipótese*) |

Perfis de apoio, sem persona própria: operador de monitoramento (E5), responsável de qualidade de
packing house (E3) e exportador (E4).

## Jornada do gestor de logística (uma viagem)

| etapa | ações | dores | oportunidades | onde o ColdTrack entra |
|---|---|---|---|---|
| **1. Antes de carregar** | Programa o veículo e o horário; confere o baú e o perfil da carga (manga ou uva) | Pré-resfriamento rápido faz diferença: na uva, 8 a 10 h até 3–4 °C [F4]; calor na rota | Escolher a janela mais fresca para carregar | Faixa pelo perfil de carga; calor previsto nas próximas 24 h na rota e janela mais fresca (Dashboard) |
| **2. Carregamento e saída** | Carrega, fecha o baú, liga o sensor, registra a viagem | Porta aberta e carga quente deixam o calor entrar [F10] | Registrar origem, destino e carga desde o início | Viagens: início da viagem; etiqueta QR no baú abre o Dashboard do veículo |
| **3. Durante a viagem** | Acompanha a frota; motorista dirige; trechos com sinal fraco | Desvio só descoberto no destino [F10]; zonas sem sinal; mangas ficam entre 8 e 10 °C sem ninguém ver [F1] | Alerta na hora, antes de a perda se consolidar | Leitura a cada 20 s, status NORMAL, ATENÇÃO, CRÍTICO, SEM SINAL; sinal luminoso no baú; fila offline reenvia depois |
| **4. Alerta ou desvio** | Confere equipamento e porta, avisa motorista e cliente | Fluxo real é *hipótese*; responsabilidade em disputa [F10] | Ação rápida e registro do que foi feito | Alertas: ocorrências com início, duração e pico |
| **5. Chegada e porto** | Entrega, recebe inspeção; armador e porto condicionam o prazo [F7]; portos sem tomada, poucos fiscais [F8] | Rejeição de carga no destino [F2]; informação desencontrada derruba lote [F8] | Entregar com o histórico da viagem anexado | Viagens: menor e maior temperatura, tempo fora da faixa, gráfico do trajeto |
| **6. Depois** | Fecha com o cliente; revê ocorrências; decide manutenção e rota | Seguro de transporte costuma excluir variação de temperatura e o registro sozinho não garante indenização [F11] | Aprender com as viagens; prova de conformidade para auditoria [F9][F10] | Relatórios por período (percentual fora da faixa, exportação CSV) |

## Proposta de valor

Canvas (tabela). Linhas de dor e ganho são as da persona acima.

| bloco | conteúdo |
|---|---|
| **Segmento de cliente** | Transportadoras refrigeradas que levam manga e uva do Vale do São Francisco aos portos; motorista e operador como usuários de apoio |
| **Tarefas do cliente** | Entregar a carga na faixa e provar isso; reagir rápido a desvio; atender exigência de rastreabilidade do exportador [F9] |
| **Dores** | Descobrir o desvio só no destino [F10]; rejeição por defeito invisível [F1][F2]; falta de prova em disputa [F10]; seguro limitado [F11]; sinal fraco na rota |
| **Ganhos esperados** | Aviso na hora; histórico por viagem; relatório para cliente; menos discussão de responsabilidade |
| **Produto** | Sensor ESP32-C3 no baú com semáforo e fila offline; API; painel web/PWA por transportadora com alertas, viagens e relatórios |
| **Aliviadores de dor** | Leitura a cada 20 s; classificação pela faixa do perfil; reenvio de leituras guardadas sem duplicar; separação de SEM SINAL e CRÍTICO; histórico e CSV |
| **Criadores de ganho** | Tempo fora da faixa por viagem; calor previsto na rota; QR no baú; várias transportadoras sem ver os dados umas das outras |
| **Promessa** | "Saber, durante a viagem, quando a carga sai da faixa, e ter o registro da viagem para mostrar." |
| **O que o produto não promete** | Indenização de seguro [F11]; diagnóstico de corte negro (é distúrbio da fruta, com fatores de manejo [F1]); substituição do termógrafo certificado exigido em contrato, se houver (*hipótese*) |

## Indicadores do painel e a decisão que apoiam

| indicador (tela) | decisão da persona | fundamento |
|---|---|---|
| Status do veículo: NORMAL, ATENÇÃO, CRÍTICO, SEM DADOS, SEM SINAL (Veículos) | Qual caminhão precisa de ação agora; separar "perigo" de "sem informação" | Desvio só visto no destino sem monitoramento contínuo [F10] |
| Temperatura atual e gráfico de 30 min com a faixa (Dashboard) | Parar, checar porta ou equipamento, ou deixar seguir | Causas comuns: porta, clima, falha de equipamento [F10] |
| Tempo na faixa de ATENÇÃO e CRÍTICO por viagem (Viagens, Alertas) | Aceitar a carga como boa, avisar o cliente antes da chegada | Manga a 8–10 °C favorece corte negro; 12,5 °C sem sintomas [F1][F2] |
| Menor e maior temperatura da viagem (Viagens) | Decidir se há risco de frio demais (manga) ou calor (uva) | Frio também estraga a manga [F1]; uva precisa estar entre 1 e 3 °C [F4] |
| Ocorrências com início, duração e pico (Alertas) | Quem acionar e como explicar o que houve | Registro serve de prova em disputa [F10] |
| Percentual fora da faixa e CSV (Relatórios) | Entregar comprovação ao exportador; revisar rota e veículo | Rastreabilidade pede dado de transporte [F9]; informação desencontrada derruba carga [F8] |
| Calor previsto 24 h na rota e janela mais fresca (Dashboard) | Quando carregar e sair | Pré-resfriamento e frio contínuo sustentam a qualidade [F4][F6] |
| Sinal e última comunicação do sensor (Sensores) | Confiar ou não no dado; manutenção | Dado sem auditoria gera desconfiança [F10]; sensor falha em silêncio (E4, hipótese) |
| Fila offline reenviada (firmware, transparente no painel) | Ter a viagem completa mesmo após trecho sem sinal | Trechos com sinal fraco na rota ([`../apresentacao.md`](../apresentacao.md)) |

## Pontos que a revisão da equipe deve olhar

1. **Faixa da uva.** O perfil do sistema para uva de mesa é de -1 a 0 °C; as fontes lidas trazem
   1 a 3 °C [F4] e 2–3 °C [F5]. Confirmar com exportador ou Embrapa antes de o material final
   afirmar a faixa.
2. **Faixa de ATENÇÃO da manga** coincide com a zona de risco do corte negro [F1]; o painel já
   mostra tempo fora da faixa por viagem. Vale conferir se o tempo em ATENÇÃO aparece de modo
   claro para essa carga.
3. Frio demais conta como desvio também (regra existente), coerente com [F1].

## O que falta validar com usuário real

Entra no roteiro e no formulário de [`../pesquisa-usuarios.md`](../pesquisa-usuarios.md):

- Como a transportadora acompanha hoje (termógrafo, telemetria, nada) e com que frequência.
- Quem é avisado e o que se faz ao receber um alerta; tempo real até agir.
- Se o motorista aceita o semáforo no baú e como ele vê o registro.
- Preço e disposição a pagar; quem decide a compra.
- Dispositivo preferido (celular ou computador) e tolerância a alertas em excesso.
- Se contratos pedem termógrafo certificado ou laudo específico.

A validação (≥ 5 entrevistas ou ≥ 20 respostas) **segue pendente para a entrega final**; este
documento deve ser revisado com as respostas reais.

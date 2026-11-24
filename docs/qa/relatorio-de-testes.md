# Relatório de testes: latência ponta a ponta (P1 a P6)

Evidência da issue #126: tempo entre um estímulo físico na placa (t0) e o valor aparecer no
painel (t1). Os números de campo anteriores (só dado gravado, sem estímulo) estão em
`analise/sensor/relatorio_campo.md` e em `RESILIENCIA.md`; este relatório traz a medição com a
placa ligada.

## Latência ao vivo (24/11/2026)

### Método

- Dispositivo `coldtrack-0e0b2c`, placa física dentro da caixa (pote fechado).
- Um coletor consultou a API e gravou cada leitura nova (`seq`, `medidoEm`, `recebidoEm`,
  `temperatura`, `umidade`, horários em UTC) a partir de 01:03 UTC de 24/11 (22:03 de 23/11 no
  horário local, UTC−3): 92 leituras, `seq` 12301 a 12392. Os mesmos valores foram conferidos
  no Cosmos (`leituras`), só com leitura. O arquivo bruto não foi versionado (o `.gitignore`
  barra `*.jsonl`); as leituras em volta dos estímulos estão na tabela do fim deste relatório.
- Estímulo: um ventilador apontado para o sensor, ligado três vezes.
- **t0 é aproximado.** Não houve cronômetro na placa: t0 é a hora em que a mensagem "liguei o
  ventilador" chegou. O ventilador foi ligado alguns segundos antes, até uns 30 s antes. Por isso
  os tempos abaixo são **cotas inferiores**: a latência real pode ser até ~30 s maior.
- Para cada estímulo: primeira leitura com temperatura diferente depois de t0;
  t_sensor = `medidoEm` − t0 (estímulo até a placa medir), t_banco = `recebidoEm` − t0 (até
  gravar na nuvem) e t_painel ≤ t_banco + 20 s, porque o painel consulta a API a cada 20 s
  (`UPDATE_INTERVAL = 20000` em `Front-End-pi/src/lib/config.js`). O painel não foi
  cronometrado na tela; t_painel é um limite calculado, não uma medição.

### Estímulos

| # | t0 (UTC, aprox.) | primeira leitura alterada | t_sensor | t_banco | t_painel (limite) | veredito |
|---|---|---|---|---|---|---|
| 1 | ~01:08 | `seq` 12346, medida 01:15:30, recebida 01:15:34,7 (33,8 → 33,3 °C) | ~7,5 min | ~7,6 min | ≤ ~7,9 min | sem degrau claro |
| 2 | ~01:21:01 | `seq` 12364, medida 01:22:09, recebida 01:22:13,3 (32,3 → 31,8 °C) | 68 s | 72,3 s | ≤ 92 s | ambíguo |
| 3 | ~01:23:56 | `seq` 12371, medida 01:24:29, recebida 01:24:37,1 (31,8 → 31,4 °C) | 33 s | 41,1 s | ≤ 61 s | parcial: mudança de inclinação visível; instante do degrau ambíguo |

Detalhe de cada um:

1. **~01:08.** A temperatura ficou parada em 33,8 °C de 01:07:29 a 01:15:09; a primeira mudança
   veio 7,5 min depois, tarde demais para atribuir ao ventilador com segurança. A umidade caiu
   devagar (58 % → 55 % entre 01:11:49 e 01:14:09). A queda anterior, 35,2 → 33,8 °C entre 01:04
   e 01:07, coincide com a caixa aberta para fotos (~01:06), não com o ventilador.
2. **~01:21:01.** A temperatura já vinha caindo antes do t0, cerca de 0,2 °C/min (degraus em
   01:15:30, 01:17:29, 01:19:49). O degrau de 01:22:09 cai no ritmo dessa tendência; não dá para
   separar o efeito do ventilador.
3. **~01:23:56.** Os dados não mostram se o ventilador estava desligado entre o estímulo 2 e o 3.
   O primeiro degrau depois do t0 (01:24:29) também caberia na tendência anterior. O que muda é a
   inclinação: nos 10 min antes do t0 a temperatura caiu 2,0 °C (33,8 em 01:13:49 → 31,8 em
   01:23:49, ~0,20 °C/min); depois do t0 caiu 2,5 °C em 6 min 40 s (31,8 em 01:24:09 → 29,3 em
   01:30:49, ~0,38 °C/min). O efeito do ventilador aparece como resfriamento quase duas vezes mais
   rápido a partir de 01:24:29, não como um degrau isolado.

**Resultado honesto:** dos três estímulos, nenhum deu um degrau limpo. A issue pede pelo menos
5 medições; **esta rodada tem 3 estímulos e só 1 com efeito visível**, então a meta de 5 não foi
cumprida e a medição deve ser repetida com um estímulo mais forte (ver "Repetição recomendada").

### Placa → banco nesta sessão

`recebidoEm` − `medidoEm` das leituras medidas entre 01:03:09 e 01:31:29 UTC (`seq` 12310 a 12392,
83 leituras). Tempo real = atraso menor que 60 s (mesmo critério do relatório de campo).
Percentil por interpolação linear.

| grupo | leituras | mediana | p95 | máximo |
|---|---|---|---|---|
| tempo real (< 60 s) | 82 | 4,65 s | 26,3 s | 53,7 s |
| reenvio (≥ 60 s) | 1 (`seq` 12310) | 67,8 s | n/a | 67,8 s |

- Mínimo 4,0 s; nenhum atraso negativo.
- `seq` 12301 a 12392 **sem buraco**: 92 de 92 leituras recebidas.
- Seis leituras passaram de 20 s, em dois episódios: 01:03 a 01:04 (`seq` 12310 a 12313, de 67,8 s
  a 20,9 s, a placa entregou em sequência o que segurou) e 01:17 a 01:19 (`seq` 12351, 12352 e
  12355: 48,6 s, 33,9 s e 26,6 s). Nos mesmos trechos, o intervalo entre medições subiu de 20 s
  para 39 a 41 s (12313 → 12314, 12352 → 12353, 12355 → 12356), com `seq` consecutivo: o envio
  lento atrasou a medição seguinte, sem perder leitura. O dado não registra a causa (Wi-Fi ou
  resposta lenta da API).
- Comparação com o histórico (`relatorio_campo.md`, 10.692 leituras de 17 a 20/11): mediana
  3,9 s e p95 7,8 s. Hoje a mediana ficou parecida (4,65 s) e o p95 subiu (26,3 s) por causa dos
  dois episódios acima; com só 82 leituras, dois episódios pesam muito no p95.

### Decomposição P1 a P6

| etapa | o que é | tempo | fonte |
|---|---|---|---|
| P1 | estímulo → sensor (DHT11 sente a mudança do ar) | segundos a minutos, depende do estímulo | resposta térmica lenta do DHT11 dentro da caixa; degraus observados de 0,1 a 0,6 °C |
| P2 | sensor → leitura da placa | 0 a 20 s (espera a próxima leitura) | ciclo de 20 s (`INTERVALO_ENVIO_PADRAO_MS`) |
| P3 | filtro de mediana da placa | até 2 ciclos (~40 s) para um degrau passar, se o filtro estiver ativo | firmware do repositório: mediana de 5 (`FILTRO_JANELA`); ver nota abaixo |
| P4 | placa → API → Cosmos | mediana 4,65 s, p95 26,3 s (hoje); mediana 3,9 s, p95 7,8 s (histórico) | `recebidoEm` − `medidoEm` |
| P5 | Cosmos → painel | 0 a 20 s | painel consulta a API a cada 20 s (`UPDATE_INTERVAL`) |
| P6 | painel desenha o valor | desprezível (milissegundos) | renderização local |

Soma, a partir do momento em que o sensor já sentiu a mudança: típico ~24 s (10 s de espera média
+ ~4 s de upload + 10 s de espera média do painel) e pior caso normal ~48 s (20 + ~8 + 20), sem
contar P1 nem o filtro.

**Nota sobre o filtro (P3):** o firmware do repositório aplica mediana de 5 leituras e manda o
valor bruto em `temperaturaBruta`. As leituras desta sessão chegaram **sem** `temperaturaBruta`
no Cosmos, então não dá para confirmar pelo dado se a placa roda essa versão com o filtro, nem
separar o atraso do filtro do atraso do sensor. Se o filtro estiver ativo, um degrau só aparece
quando 3 das 5 leituras mudam, o que soma até ~40 s.

### Por que passa de 40 s (2 intervalos de envio)

O critério da issue manda explicar quando t1 − t0 passa de 40 s. Nesta rodada passou nos três
estímulos (t_banco de 41 s a 7,6 min, contando do t0 aproximado). As causas, em ordem de peso:

1. **P1, inércia térmica do sensor.** O DHT11 fica dentro de uma caixa e mede o ar em volta; um
   ventilador soprando ar ambiente, não muito mais frio que a caixa, muda a
   temperatura devagar. A mudança aparece como inclinação ao longo de minutos, não como degrau.
   Isso sozinho explica os casos 1 e 2.
2. **P2 + P5, os dois ciclos de 20 s.** Mesmo com o sensor instantâneo, a espera pela próxima
   leitura (até 20 s) e pela próxima consulta do painel (até 20 s) somam até 40 s. Com o upload
   (~4 s) por cima, o pior caso normal já passa de 40 s.
3. **P3, filtro de mediana** (se ativo na placa): até ~40 s a mais para um degrau aparecer.
4. **t0 aproximado.** t0 é a chegada da mensagem, não o clique no ventilador; o erro é de alguns
   segundos até ~30 s e empurra os números para cima ou para baixo dentro dessa faixa.
5. **Envio lento ocasional (P4).** Em dois episódios o upload levou de 20 a 68 s e atrasou a
   medição seguinte (ver a seção anterior).

Conclusão: a cadeia digital (P2 a P6) fica tipicamente em ~24 s e no pior caso normal em ~48 s.
O que leva a latência medida para minutos é a resposta física do sensor (P1) a um estímulo
fraco, não a rede nem a nuvem.

### Repetição recomendada

Para fechar as 5 medições com degraus claros:

- Usar um objeto frio (gelo em saco plástico ou bolsa térmica) encostado perto do sensor, que
  muda a temperatura vários graus em segundos, em vez de ventilador com ar quase na mesma
  temperatura.
- Cronometrar t0 de verdade (foto ou vídeo do relógio no instante do estímulo) e t1 na tela do
  painel, em vez da hora da mensagem.
- Esperar a temperatura estabilizar (sem tendência) antes de cada estímulo, para o degrau não se
  confundir com a deriva.
- Conferir se a placa manda `temperaturaBruta`, para separar o atraso do filtro de mediana.

### Leituras em volta dos estímulos

De 01:05:49 a 01:31:29 UTC (24/11/2026), na ordem da `seq`.

| `seq` | medida (UTC) | recebida (UTC) | atraso (s) | temperatura (°C) | umidade (%) |
|---|---|---|---|---|---|
| 12317 | 01:05:49 | 01:05:53,2 | 4,2 | 34,2 | 56 |
| 12318 | 01:06:09 | 01:06:13,4 | 4,4 | 34,2 | 56 |
| 12319 | 01:06:29 | 01:06:42,4 | 13,4 | 34,2 | 56 |
| 12320 | 01:06:49 | 01:06:53,3 | 4,4 | 34,2 | 57 |
| 12321 | 01:07:09 | 01:07:13,3 | 4,3 | 34,2 | 57 |
| 12322 | 01:07:29 | 01:07:33,1 | 4,2 | 33,8 | 57 |
| 12323 | 01:07:50 | 01:07:54,2 | 4,3 | 33,8 | 58 |
| 12324 | 01:08:09 | 01:08:13,3 | 4,3 | 33,8 | 58 |
| 12325 | 01:08:29 | 01:08:36,9 | 7,9 | 33,8 | 58 |
| 12326 | 01:08:50 | 01:08:58,3 | 8,4 | 33,8 | 58 |
| 12327 | 01:09:09 | 01:09:13,3 | 4,4 | 33,8 | 58 |
| 12328 | 01:09:29 | 01:09:33,4 | 4,5 | 33,8 | 58 |
| 12329 | 01:09:49 | 01:09:53,1 | 4,2 | 33,8 | 58 |
| 12330 | 01:10:09 | 01:10:13,3 | 4,3 | 33,8 | 58 |
| 12331 | 01:10:29 | 01:10:33,0 | 4,0 | 33,8 | 58 |
| 12332 | 01:10:49 | 01:10:53,1 | 4,2 | 33,8 | 58 |
| 12333 | 01:11:09 | 01:11:13,0 | 4,1 | 33,8 | 58 |
| 12334 | 01:11:29 | 01:11:36,2 | 7,2 | 33,8 | 58 |
| 12335 | 01:11:49 | 01:11:53,5 | 4,6 | 33,8 | 57 |
| 12336 | 01:12:09 | 01:12:14,0 | 5,0 | 33,8 | 57 |
| 12337 | 01:12:29 | 01:12:36,4 | 7,4 | 33,8 | 57 |
| 12338 | 01:12:49 | 01:12:53,0 | 4,1 | 33,8 | 56 |
| 12339 | 01:13:09 | 01:13:13,7 | 4,7 | 33,8 | 56 |
| 12340 | 01:13:29 | 01:13:33,3 | 4,4 | 33,8 | 56 |
| 12341 | 01:13:49 | 01:13:53,1 | 4,2 | 33,8 | 56 |
| 12342 | 01:14:09 | 01:14:13,5 | 4,5 | 33,8 | 55 |
| 12343 | 01:14:29 | 01:14:36,9 | 8,0 | 33,8 | 55 |
| 12344 | 01:14:49 | 01:14:53,2 | 4,3 | 33,8 | 55 |
| 12345 | 01:15:09 | 01:15:15,6 | 6,6 | 33,8 | 54 |
| 12346 | 01:15:30 | 01:15:34,6 | 4,7 | 33,3 | 54 |
| 12347 | 01:15:49 | 01:15:52,9 | 4,0 | 33,3 | 54 |
| 12348 | 01:16:09 | 01:16:13,2 | 4,2 | 33,3 | 54 |
| 12349 | 01:16:30 | 01:16:37,1 | 7,2 | 33,3 | 53 |
| 12350 | 01:16:49 | 01:16:57,3 | 8,3 | 33,3 | 53 |
| 12351 | 01:17:09 | 01:17:57,6 | 48,6 | 33,3 | 53 |
| 12352 | 01:17:29 | 01:18:02,8 | 33,9 | 32,9 | 54 |
| 12353 | 01:18:10 | 01:18:15,0 | 5,0 | 32,8 | 53 |
| 12354 | 01:18:30 | 01:18:41,2 | 11,2 | 32,8 | 53 |
| 12355 | 01:18:50 | 01:19:16,6 | 26,6 | 32,8 | 52 |
| 12356 | 01:19:29 | 01:19:36,5 | 7,5 | 32,8 | 52 |
| 12357 | 01:19:49 | 01:19:53,0 | 4,1 | 32,3 | 52 |
| 12358 | 01:20:09 | 01:20:13,3 | 4,4 | 32,3 | 52 |
| 12359 | 01:20:29 | 01:20:33,4 | 4,5 | 32,3 | 52 |
| 12360 | 01:20:49 | 01:20:57,0 | 8,1 | 32,3 | 52 |
| 12361 | 01:21:09 | 01:21:19,2 | 10,2 | 32,3 | 51 |
| 12362 | 01:21:29 | 01:21:48,0 | 19,1 | 32,3 | 51 |
| 12363 | 01:21:49 | 01:21:53,1 | 4,2 | 32,3 | 51 |
| 12364 | 01:22:09 | 01:22:13,3 | 4,3 | 31,8 | 51 |
| 12365 | 01:22:29 | 01:22:33,7 | 4,8 | 31,8 | 51 |
| 12366 | 01:22:49 | 01:22:53,6 | 4,7 | 31,8 | 50 |
| 12367 | 01:23:10 | 01:23:14,3 | 4,4 | 31,8 | 50 |
| 12368 | 01:23:29 | 01:23:33,6 | 4,6 | 31,8 | 50 |
| 12369 | 01:23:49 | 01:23:53,3 | 4,4 | 31,8 | 50 |
| 12370 | 01:24:09 | 01:24:13,3 | 4,4 | 31,8 | 49 |
| 12371 | 01:24:29 | 01:24:37,0 | 8,1 | 31,4 | 49 |
| 12372 | 01:24:49 | 01:24:56,3 | 7,4 | 31,3 | 49 |
| 12373 | 01:25:09 | 01:25:13,9 | 5,0 | 31,3 | 49 |
| 12374 | 01:25:29 | 01:25:33,1 | 4,2 | 31,3 | 48 |
| 12375 | 01:25:49 | 01:25:53,9 | 5,0 | 31 | 48 |
| 12376 | 01:26:09 | 01:26:15,7 | 6,8 | 30,8 | 48 |
| 12377 | 01:26:30 | 01:26:37,7 | 7,7 | 30,8 | 48 |
| 12378 | 01:26:49 | 01:26:53,1 | 4,1 | 30,8 | 48 |
| 12379 | 01:27:09 | 01:27:16,6 | 7,7 | 30,8 | 48 |
| 12380 | 01:27:29 | 01:27:44,9 | 16,0 | 30,2 | 47 |
| 12381 | 01:27:49 | 01:27:53,5 | 4,6 | 30,2 | 47 |
| 12382 | 01:28:09 | 01:28:13,3 | 4,4 | 30,2 | 47 |
| 12383 | 01:28:29 | 01:28:34,2 | 5,3 | 30,2 | 47 |
| 12384 | 01:28:49 | 01:28:53,2 | 4,3 | 29,8 | 48 |
| 12385 | 01:29:09 | 01:29:16,3 | 7,3 | 29,8 | 48 |
| 12386 | 01:29:29 | 01:29:33,2 | 4,3 | 29,8 | 48 |
| 12387 | 01:29:49 | 01:29:58,2 | 9,3 | 29,8 | 48 |
| 12388 | 01:30:09 | 01:30:13,3 | 4,3 | 29,3 | 48 |
| 12389 | 01:30:29 | 01:30:38,3 | 9,3 | 29,3 | 48 |
| 12390 | 01:30:49 | 01:30:57,7 | 8,7 | 29,3 | 48 |
| 12391 | 01:31:09 | 01:31:15,7 | 6,7 | 29,3 | 48 |
| 12392 | 01:31:29 | 01:31:33,3 | 4,3 | 29,3 | 48 |

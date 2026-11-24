# Previsão da temperatura do sensor (10 min à frente)

Gerado por `modelo_previsao.py` em 2026-11-24 01:38 UTC, a partir de `dados/cosmos_leituras.csv` (Cosmos DB de produção, leituras da placa ESP32-C3 + DHT11 da equipe, em bancada). Exporta `cloud/function/modelo_sensor.json`, lido pela rota `GET /api/predict/sensor`.

## Problema

Estimar a temperatura da carga daqui a 10 minutos a partir das últimas leituras do próprio sensor, para avisar antes de a leitura sair da faixa do perfil de carga. Apoia uma decisão humana (conferir a porta, o equipamento de frio, a rota); não dispara ação automática.

## Limpeza

| passo | removidas | restantes |
|---|---|---|
| leituras no CSV | 0 | 12238 |
| sem temperatura ou sem data | 0 | 12238 |
| fora da faixa do DHT11 (0 a 50 °C) | 0 | 12238 |
| instante repetido | 0 | 12238 |

Cadência medida: mediana 20 s entre leituras na base inteira e 20 s no trecho mais recente; 71.1 h de amostras no total. Trecho contínuo = sem intervalo maior que 300 s; 6 trechos geraram amostras (um instante por minuto, com 10 min de histórico e o alvo 10 min depois dentro do mesmo trecho). Valor entre leituras = última leitura até o instante.

## Divisão temporal

| conjunto | de (UTC) | até (UTC) | amostras |
|---|---|---|---|
| treino | 2026-11-17T02:44 | 2026-11-19T05:27 | 2975 |
| teste | 2026-11-19T05:38 | 2026-11-24T01:25 | 1280 |

Teste = 30% mais recentes dos instantes (corte 2026-11-19 05:38 UTC). Amostras de treino cujo alvo cai depois do corte foram descartadas.

## Resultado (teste)

| métrica | modelo (ridge) | baseline (persistência) |
|---|---|---|
| MAE (°C) | 0.383 | 0.364 |
| RMSE (°C) | 0.742 | 0.723 |

**O modelo NÃO supera o baseline** no teste: MAE 0.383 °C contra 0.364 °C da persistência. A rota continua devolvendo as duas previsões, mas recomenda a persistência (`recomendada = baseline`) até um novo treino mostrar ganho.

## Janela com excursão provocada (recorte do teste)

Sessão em bancada (2026-11-23 22:00 a 2026-11-24 02:00 UTC): placa numa panela fechada aquecendo até ~35 °C, depois panela aberta com ventilador, esfriando. É o caso que o modelo deveria antecipar. Recorte do mesmo teste, mesmos coeficientes: 44 amostras.

| recorte | amostras | MAE modelo (ridge) | MAE baseline (persistência) | MAE tendência (y0 + d10, sem treino) |
|---|---|---|---|---|
| teste inteiro | 1280 | 0.383 | 0.364 | 0.556 |
| janela com excursão | 44 | 1.608 | 1.496 | 1.066 |

A tendência é só referência e não foi escolhida por este recorte: ela erra menos que a persistência durante a excursão, mas erra bem mais no teste inteiro (ruído de degrau do DHT11 vira tendência falsa), então não é recomendada. O veredito usa só o teste inteiro.

Coeficientes (variação prevista = soma de coeficiente × atributo, sem intercepto, lambda = 1.0):

| atributo | significado | coeficiente |
|---|---|---|
| d5 | última leitura menos a de 5 min antes | +0.0083 |
| d10 | última leitura menos a de 10 min antes | -0.0004 |
| m10 | média dos últimos 10 min menos a última leitura | +0.2729 |

## Sensibilidade ao corte (informativo, não usado para escolher nada)

| fração de teste | corte (UTC) | treino | teste | MAE modelo | MAE baseline | RMSE modelo | RMSE baseline |
|---|---|---|---|---|---|---|---|
| 20% | 2026-11-19 18:32 | 3402 | 853 | 0.480 | 0.454 | 0.888 | 0.858 |
| 30% | 2026-11-19 05:38 | 2975 | 1280 | 0.383 | 0.364 | 0.742 | 0.723 |
| 40% | 2026-11-18 22:32 | 2549 | 1706 | 0.337 | 0.323 | 0.659 | 0.646 |

## Verificação cruzada

Mesmo pipeline (mesmos atributos, lambda e 30% de teste) sobre `dados/thingspeak_3515173.csv`, só para conferir que o resultado não depende da fonte:

| treino | teste | MAE modelo | MAE baseline | RMSE modelo | RMSE baseline |
|---|---|---|---|---|---|
| 3026 | 1302 | 0.346 | 0.311 | 0.674 | 0.641 |

## Limitações

- Dados limitados: 71 h de amostras em 6 trechos separados por lacunas (a placa ficou desligada ou sem rede entre eles).
- Outras tentativas fora do pipeline (regressão pela mediana, gradient boosting com erro absoluto, janela de 30 min com mais atributos, hora do dia) também não passaram da persistência no MAE; o resumo está em `docs/model-card.md`.
- Sensor em bancada, em ambiente interno, não dentro de um baú refrigerado: não há excursão real de transporte (porta aberta, falha do frio) na base. A única excursão é a provocada em bancada (seção acima), curta e inteira no teste, então o treino não tem nenhuma subida ou descida forte para aprender. Fora dela a série é quase estável e varia em degraus de resolução do DHT11, cenário em que a persistência é difícil de bater.
- O modelo não sabe nada de clima, rota ou porta: só extrapola a própria série.

## Re-treinar

```bash
cd analise/sensor
python descrever_cosmos.py --converter <export>/leituras.jsonl   # export do backup
python modelo_previsao.py            # treina, avalia e exporta
python modelo_previsao.py --baixar   # antes, atualiza o CSV do ThingSpeak (verificação)
```

![teste](figuras/previsao_teste.png)

# Previsão da temperatura do sensor (10 min à frente)

Gerado por `modelo_previsao.py` em 2026-11-23 13:59 UTC, a partir de `dados/cosmos_leituras.csv` (Cosmos DB de produção, leituras da placa ESP32-C3 + DHT11 da equipe, em bancada). Exporta `cloud/function/modelo_sensor.json`, lido pela rota `GET /api/predict/sensor`.

## Problema

Estimar a temperatura da carga daqui a 10 minutos a partir das últimas leituras do próprio sensor, para avisar antes de a leitura sair da faixa do perfil de carga. Apoia uma decisão humana (conferir a porta, o equipamento de frio, a rota); não dispara ação automática.

## Limpeza

| passo | removidas | restantes |
|---|---|---|
| leituras no CSV | 0 | 12015 |
| sem temperatura ou sem data | 0 | 12015 |
| fora da faixa do DHT11 (0 a 50 °C) | 0 | 12015 |
| instante repetido | 0 | 12015 |

Cadência medida: mediana 20 s entre leituras na base inteira e 20 s no trecho mais recente; 70.3 h de amostras no total. Trecho contínuo = sem intervalo maior que 300 s; 5 trechos geraram amostras (um instante por minuto, com 10 min de histórico e o alvo 10 min depois dentro do mesmo trecho). Valor entre leituras = última leitura até o instante.

## Divisão temporal

| conjunto | de (UTC) | até (UTC) | amostras |
|---|---|---|---|
| treino | 2026-11-17T02:44 | 2026-11-19T04:56 | 2944 |
| teste | 2026-11-19T05:07 | 2026-11-20T08:00 | 1267 |

Teste = 30% mais recentes dos instantes (corte 2026-11-19 05:07 UTC). Amostras de treino cujo alvo cai depois do corte foram descartadas.

## Resultado (teste)

| métrica | modelo (ridge) | baseline (persistência) |
|---|---|---|
| MAE (°C) | 0.334 | 0.319 |
| RMSE (°C) | 0.662 | 0.652 |

**O modelo NÃO supera o baseline** no teste: MAE 0.334 °C contra 0.319 °C da persistência. A rota continua devolvendo as duas previsões, mas recomenda a persistência (`recomendada = baseline`) até um novo treino mostrar ganho.

Coeficientes (variação prevista = soma de coeficiente × atributo, sem intercepto, lambda = 1.0):

| atributo | significado | coeficiente |
|---|---|---|
| d5 | última leitura menos a de 5 min antes | +0.0080 |
| d10 | última leitura menos a de 10 min antes | -0.0007 |
| m10 | média dos últimos 10 min menos a última leitura | +0.2713 |

## Sensibilidade ao corte (informativo, não usado para escolher nada)

| fração de teste | corte (UTC) | treino | teste | MAE modelo | MAE baseline | RMSE modelo | RMSE baseline |
|---|---|---|---|---|---|---|---|
| 20% | 2026-11-19 17:56 | 3366 | 845 | 0.406 | 0.386 | 0.786 | 0.768 |
| 30% | 2026-11-19 05:07 | 2944 | 1267 | 0.334 | 0.319 | 0.662 | 0.652 |
| 40% | 2026-11-18 22:05 | 2522 | 1689 | 0.302 | 0.292 | 0.593 | 0.588 |

## Verificação cruzada

Mesmo pipeline (mesmos atributos, lambda e 30% de teste) sobre `dados/thingspeak_3515173.csv`, só para conferir que o resultado não depende da fonte:

| treino | teste | MAE modelo | MAE baseline | RMSE modelo | RMSE baseline |
|---|---|---|---|---|---|
| 3026 | 1302 | 0.346 | 0.311 | 0.674 | 0.641 |

## Limitações

- Dados limitados: 70 h de amostras em 5 trechos separados por lacunas (a placa ficou desligada ou sem rede entre eles).
- Outras tentativas fora do pipeline (regressão pela mediana, gradient boosting com erro absoluto, janela de 30 min com mais atributos, hora do dia) também não passaram da persistência no MAE; o resumo está em `docs/model-card.md`.
- Sensor em bancada, em ambiente interno, não dentro de um baú refrigerado: não há nenhuma excursão térmica real (porta aberta, falha do frio) na base. A série é quase estável e varia em degraus de resolução do DHT11, cenário em que a persistência é difícil de bater.
- O modelo não sabe nada de clima, rota ou porta: só extrapola a própria série.

## Re-treinar

```bash
cd analise/sensor
python descrever_cosmos.py --converter <export>/leituras.jsonl   # export do backup
python modelo_previsao.py            # treina, avalia e exporta
python modelo_previsao.py --baixar   # antes, atualiza o CSV do ThingSpeak (verificação)
```

![teste](figuras/previsao_teste.png)

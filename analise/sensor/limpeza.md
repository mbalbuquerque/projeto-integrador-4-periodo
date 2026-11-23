# Limpeza da base do sensor

Gerado por `limpar_sensor.py` a partir do container `leituras` do Cosmos (export de 17 a 20/11/2026). Requisito do plano de ação (#138). Os números saem todos do export; nada é estimado à mão. O export bruto tem endereço de e-mail em outros containers e fica fora do repositório; só o CSV sem dado pessoal (`dados/cosmos_leituras.csv`) é versionado.

## Passo a passo

| passo | removidas | restantes |
|---|---|---|
| leituras no container | 0 | 16100 |
| de outro dispositivo (testes de push) | 12 | 16088 |
| sem número de sequência (`seq`) | 4073 | 12015 |
| `seq` repetido (reenvio idêntico) | 0 | 12015 |
| sem data ou sem temperatura | 0 | 12015 |
| temperatura fora de 0 a 50 °C (faixa do DHT11) | 0 | 12015 |
| umidade fora de 20 a 90 % (faixa do DHT11) | 0 | 12015 |
| instante repetido | 0 | 12015 |

A base limpa tem **12015 leituras**, de 17/11 02:33 a 20/11 08:10 UTC (77.6 h entre a primeira e a última).

## O que cada passo trata

- **Outro dispositivo:** leituras `teste-push*`, enviadas para testar o alerta push; não são da placa.
- **Sem `seq`:** leituras gravadas antes de o firmware numerar as mensagens (R3); sem número não dá para medir perda nem detectar duplicata.
- **`seq` repetido:** reenvio idêntico da fila; a API já responde `duplicada`, e este passo garante a mesma regra na análise.
- **Sem data ou temperatura:** leitura que o DHT não conseguiu fazer (a placa marca como inválida e não grava como válida; aqui é só a segunda barreira).
- **Fora da faixa:** valores fisicamente impossíveis para o DHT11 (datasheet: 0 a 50 °C e 20 a 90 % de umidade).
- **Instante repetido:** duas leituras no mesmo segundo (a série do modelo precisa de instantes únicos).

## Lacunas e perda (não removem leitura)

- Lacunas maiores que 2 min na base limpa: **7** (maior: 286.7 min).
- Números de `seq` faltando entre o menor e o maior: **103** (0.85% da faixa).
- O modelo quebra a série em trechos nas lacunas (`LACUNA_S` em `modelo_previsao.py`), então nenhum alvo atravessa um buraco.

## Ligação com o modelo

`dados/cosmos_leituras.csv`, que alimenta `modelo_previsao.py`, tem 12015 linhas; esta limpeza deixa 12015 (mesma quantidade). Todas as `seq` do CSV estão na base limpa: **sim**. Depois disso `modelo_previsao.py` ainda descarta, na temperatura, vazio, fora de 0 a 50 °C e instante repetido (a tabela de limpeza dele, em `relatorio_previsao.md`).

## Reproduzir

```
python infra/backup/exportar.py <pasta-fora-do-repo> --excluir limites usuarios
python analise/sensor/limpar_sensor.py <pasta>/leituras.jsonl --gerar
```

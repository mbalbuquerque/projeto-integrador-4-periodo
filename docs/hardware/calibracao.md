# Calibração do sensor contra uma referência

**Situação: procedimento pronto, medição pendente.** Precisa da placa e de um termo-higrômetro
de referência; nenhuma medição foi registrada ainda.

## Material

- Placa ColdTrack com o DHT11 montado como ficará na caixa.
- Referência: termo-higrômetro digital com certificado ou, no mínimo, instrumento de precisão
  melhor que a do DHT11 (±2 °C, ±5 % UR). Anotar modelo e precisão declarada.
- Ambiente estável (sala fechada, sem ar-condicionado soprando direto), sensores lado a lado.

## Procedimento

1. Ligar a placa e a referência juntas e esperar 15 min para estabilizar.
2. Coletar pelo menos 3 pontos de temperatura (por exemplo ~20, ~30 e ~35 °C, em horários
   diferentes) e 2 de umidade.
3. Em cada ponto, anotar 10 leituras da placa (monitor serial ou `GET /api/leituras`) e 10 da
   referência, com o horário.
4. Calcular a média da placa, a média da referência e o desvio (placa − referência).
5. Se o desvio médio for estável, registrar o ajuste (offset) e aplicá-lo na API ou no
   firmware; se variar com a temperatura, usar reta (ganho + offset) por mínimos quadrados.
6. Repetir 3 leituras depois de aplicar o ajuste e registrar o desvio residual.

## Tabela de registro

| Data | Grandeza | Ponto | Média placa | Média referência | Desvio | Observação |
|---|---|---|---|---|---|---|
| | temperatura (°C) | 1 | | | | |
| | temperatura (°C) | 2 | | | | |
| | temperatura (°C) | 3 | | | | |
| | umidade (%) | 1 | | | | |
| | umidade (%) | 2 | | | | |

| Resultado | Valor |
|---|---|
| Referência usada (modelo e precisão) | |
| Offset de temperatura (°C) | |
| Offset de umidade (%) | |
| Desvio residual depois do ajuste | |
| Responsável e data | |
